"""파트 B 검증 결과의 출처와 실행 환경을 기록한다."""
import datetime
import glob
import json
import platform
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent


def git(*args):
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git 실행 실패")
    return result.stdout.strip()


def metadata():
    return {
        "recorded_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "commit": git("rev-parse", "HEAD"),
        "branch": git("branch", "--show-current"),
        "dirty": bool(git("status", "--porcelain")),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.node(),
        "processor": platform.processor(),
    }


def require_clean():
    if git("status", "--porcelain"):
        raise SystemExit("검증 스크립트를 먼저 커밋하세요. 측정 로그에 dirty 코드를 섞지 않습니다.")


def files_from(inputs, suffix=".jsonl"):
    files = set()
    for value in inputs:
        p = Path(value)
        if p.is_dir():
            files.update(p.rglob("*" + suffix))
        else:
            files.update(Path(v) for v in glob.glob(value))
    return sorted(files)


def read_rows(files):
    rows = []
    for path in files:
        for line_no, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            if line.strip():
                row = json.loads(line)
                row["_src"] = f"{path}:{line_no}"
                rows.append(row)
    return rows


def finish(report, out=None):
    report["environment"] = metadata()
    if out:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    brief = {k: v for k, v in report.items() if k not in ("details", "groups", "files", "hashes", "environment")}
    print(json.dumps(brief, ensure_ascii=False, indent=2))
    if out:
        print(f"상세 결과: {Path(out).resolve()}")
    return 1 if report["status"] == "fail" else 0

