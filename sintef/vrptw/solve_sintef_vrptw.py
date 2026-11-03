#!/usr/bin/env python3
"""解压 SINTEF VRPTW 算例包，逐个调用 yunpyopt 求解，并把结果回填到登记表 CSV。

用法::

    python sintef/vrptw/solve_sintef_vrptw.py
    python sintef/vrptw/solve_sintef_vrptw.py --jobs 4 --only c1_2_1 r2_2_3
    python sintef/vrptw/solve_sintef_vrptw.py --skip-filled

算例从 ``<zip-dir>/<instance>.zip`` 解压到 ``<work-dir>/<instance>/``，求解产物
（``output/<request_id>/``）留在工作目录，不写入仓库。CSV 的 ``Bks*`` 列原样保留，
只回填 ``Yun*`` 与 ``Gap*`` 列，每完成一个算例就原子重写一次，便于中断续跑。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import tempfile
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

CSV_FIELDS = [
    "Instance",
    "BksVehicle",
    "BksDistance",
    "YunVehicle",
    "YunDistance",
    "GapVehicle",
    "GapDistance",
]

# PlanSummary.TotalTravelDistance 的单位是米；SINTEF 的距离单位是 1000 米。
METERS_PER_DISTANCE_UNIT = 1000.0

# 解压后必须存在的文件，用来判断算例目录是否完整。
CASE_FILES = (
    "Parameter.yaml",
    "Strategy.lua",
    "Location.csv",
    "CargoOrder.csv",
    "Vehicle.csv",
    "DistMatrix.csv",
)

JUNK_SUFFIXES = (".DS_Store",)


def log(message: str) -> None:
    print(message, flush=True)


def is_junk(member: str) -> bool:
    parts = member.split("/")
    name = parts[-1]
    return (
        "__MACOSX" in parts
        or name == ""
        or name.startswith("._")
        or name in JUNK_SUFFIXES
        or not member
    )


def case_ready(case_dir: Path) -> bool:
    return all((case_dir / name).is_file() for name in CASE_FILES)


def extract_cases(zip_dir: Path, work_dir: Path, names: list[str], force: bool) -> dict[str, Path]:
    """把 ``names`` 对应的 zip 解压到 ``work_dir``，返回算例目录映射。"""
    work_dir.mkdir(parents=True, exist_ok=True)
    case_dirs: dict[str, Path] = {}
    for name in names:
        archive = zip_dir / f"{name}.zip"
        if not archive.is_file():
            raise FileNotFoundError(f"缺少算例包：{archive}")
        target = work_dir / name
        if force and target.exists():
            shutil.rmtree(target)
        if case_ready(target):
            case_dirs[name] = target
            continue
        if target.exists():
            shutil.rmtree(target)
        with zipfile.ZipFile(archive) as handle:
            members = []
            for info in handle.infolist():
                member = info.filename
                if is_junk(member):
                    continue
                resolved = (work_dir / member).resolve()
                if work_dir.resolve() not in resolved.parents and resolved != work_dir.resolve():
                    raise ValueError(f"{archive} 含越界路径：{member}")
                members.append(info)
            handle.extractall(work_dir, members=members)
        if not case_ready(target):
            raise ValueError(f"{archive} 解压后缺少必需文件：{target}")
        case_dirs[name] = target
    return case_dirs


def solve_one(task: tuple[str, str, str]) -> dict[str, Any]:
    """在子进程中求解单个算例。``task`` 为 (instance, case_dir, log_level)。"""
    name, case_dir, log_level = task
    from yunpyopt import solve

    started = time.time()
    try:
        result = solve(case_dir, log_level=log_level)
    except Exception as exc:  # 求解器抛出的异常统一记录，不中断整批
        return {
            "instance": name,
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed_second": round(time.time() - started, 1),
        }

    elapsed = round(time.time() - started, 1)
    summary_path = result.get("plan_summary")
    if not summary_path:
        return {
            "instance": name,
            "error": "precheck 拦截，未生成 PlanSummary",
            "infeasible": result.get("infeasible"),
            "elapsed_second": elapsed,
        }

    summary = json.loads(Path(summary_path).read_text(encoding="utf-8"))
    distance_units = summary["TotalTravelDistance"] / METERS_PER_DISTANCE_UNIT
    return {
        "instance": name,
        "vehicles": int(summary["TotalLoadCount"]),
        "distance": distance_units,
        "unassigned": int(summary.get("UnassignedCargoOrderCount", 0)),
        "total_orders": int(summary.get("TotalCargoOrderCount", 0)),
        "running_second": summary.get("RunningTimeSecond"),
        "elapsed_second": elapsed,
        "plan_summary": str(summary_path),
    }


def read_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or [field.strip() for field in reader.fieldnames] != CSV_FIELDS:
            raise ValueError(f"{csv_path} 表头不符合约定：{reader.fieldnames}")
        return [dict(row) for row in reader]


def write_rows(csv_path: Path, rows: list[dict[str, str]]) -> None:
    tmp_path = csv_path.with_suffix(csv_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp_path, csv_path)


def fill_row(row: dict[str, str], result: dict[str, Any]) -> dict[str, str]:
    """把单个求解结果写入 CSV 行（只动 Yun*/Gap* 四列）。"""
    bks_vehicle = int(row["BksVehicle"])
    bks_distance = float(row["BksDistance"])
    yun_vehicle = result["vehicles"]
    yun_distance = result["distance"]
    row["YunVehicle"] = str(yun_vehicle)
    row["YunDistance"] = f"{yun_distance:.2f}"
    row["GapVehicle"] = str(yun_vehicle - bks_vehicle)
    row["GapDistance"] = f"{abs(yun_distance - bks_distance) / bks_distance:.2f}"
    return row


def format_duration(seconds: float) -> str:
    minutes, rest = divmod(int(seconds), 60)
    return f"{minutes}m{rest:02d}s"


def main(argv: list[str] | None = None) -> int:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--zip-dir", type=Path, default=script_dir / "200customers", help="算例 zip 所在目录")
    parser.add_argument(
        "--csv",
        type=Path,
        default=script_dir.parent / "SINTER_VRPTW_INSTANCE.csv",
        help="结果登记表 CSV",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=Path(tempfile.gettempdir()) / "yun_sintef_vrptw" / "200customers",
        help="解压与求解产物的临时目录",
    )
    parser.add_argument("--jobs", type=int, default=4, help="并行求解的算例数（每个算例的 ALNS 自身还会用 4 线程）")
    parser.add_argument(
        "--only",
        nargs="+",
        metavar="INSTANCE",
        help="只求解指定算例（调试用），默认求解 CSV 中的全部算例",
    )
    parser.add_argument("--log-level", default="warn", help="求解器日志级别")
    parser.add_argument("--skip-filled", action="store_true", help="跳过 CSV 中已回填 Yun 结果的算例")
    parser.add_argument("--reextract", action="store_true", help="重新解压算例目录")
    args = parser.parse_args(argv)

    rows = read_rows(args.csv)
    by_name = {row["Instance"]: row for row in rows}
    names = [row["Instance"] for row in rows]
    if args.only:
        missing = [name for name in args.only if name not in by_name]
        if missing:
            parser.error(f"CSV 中没有这些算例：{', '.join(missing)}")
        names = [name for name in names if name in set(args.only)]
    if args.skip_filled:
        names = [name for name in names if not by_name[name]["YunVehicle"]]
    if not names:
        log("没有需要求解的算例。")
        return 0

    log(f"算例目录：{args.zip_dir}")
    log(f"工作目录：{args.work_dir}")
    log(f"结果 CSV：{args.csv}")
    log(f"待求解：{len(names)} 个，并行度 {args.jobs}")

    case_dirs = extract_cases(args.zip_dir, args.work_dir, names, force=args.reextract)

    tasks = [(name, str(case_dirs[name]), args.log_level) for name in names]
    started = time.time()
    done = 0
    failures: list[dict[str, Any]] = []
    results: dict[str, dict[str, Any]] = {}

    with ProcessPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = {pool.submit(solve_one, task): task[0] for task in tasks}
        for future in as_completed(futures):
            name = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # 子进程崩溃等
                result = {"instance": name, "error": f"{type(exc).__name__}: {exc}"}
            done += 1
            elapsed = time.time() - started
            eta = elapsed / done * (len(names) - done)

            if "error" in result:
                failures.append(result)
                log(f"[{done}/{len(names)}] {name} 失败：{result['error']}（eta {format_duration(eta)}）")
                continue

            row = fill_row(by_name[name], result)
            write_rows(args.csv, rows)
            results[name] = result
            flag = ""
            if result["unassigned"]:
                flag = f"  [WARN 未分配 {result['unassigned']}/{result['total_orders']} 单]"
            log(
                f"[{done}/{len(names)}] {name}: 车次 {row['YunVehicle']}（BKS {row['BksVehicle']}，"
                f"gap {row['GapVehicle']}），距离 {row['YunDistance']}（BKS {row['BksDistance']}，"
                f"gap {row['GapDistance']}），耗时 {result['elapsed_second']}s{flag}"
                f"（eta {format_duration(eta)}）"
            )

    manifest = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "zip_dir": str(args.zip_dir),
        "csv": str(args.csv),
        "jobs": args.jobs,
        "results": results,
        "failures": failures,
    }
    manifest_path = args.work_dir / "solve_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    log(f"完成 {len(results)}/{len(names)}，失败 {len(failures)}，总耗时 {format_duration(time.time() - started)}")
    log(f"求解清单：{manifest_path}")
    if failures:
        log("失败清单：")
        for item in failures:
            log(f"  - {item['instance']}: {item['error']}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
