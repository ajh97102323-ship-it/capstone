"""PreToolUse 훅: 생성물 보호 (settings.json의 deny/ask 규칙을 받치는 백업 장치).

권한 규칙의 경로 패턴은 Windows 경로 표기(대소문자, \\ 와 /, ..)나 셸 명령의 인자 순서에 따라
빠져나갈 수 있으므로, 여기서는 실제 경로를 계산해 판정한다.

- 파일 도구(Edit/Write/MultiEdit/NotebookEdit)
  - deny: reports/**, models/**, data/datasets/** (스크립트만 쓰는 생성물)
  - ask : physics/** (물리 코드가 바뀌면 생성한 데이터 1만 개와 학습 모델이 모두 무효가 됨)
- 셸(Bash/PowerShell)
  - deny: 재귀 삭제(rm -r/-R/--recursive, Remove-Item -Recurse, rmdir /s, shutil.rmtree)
  - ask : 쓰기 대상이 저장소의 physics/ 아래인 셸 명령
          (리다이렉트 > >>, sed/perl -i, tee, Set-Content/Add-Content/Out-File, cp/mv/Copy-Item의 대상,
           rm/del, git checkout/restore, python의 open(...,'w'), Path(...).write_text, shutil.copy 등)
          physics를 읽기만 하는 명령, 임시 폴더 사본을 고치는 명령, 메모리 안의 변이 확인은 통과한다.
          명령 문자열에 경로가 드러나지 않는 쓰기(스크립트 파일 안, 변수로 만든 경로)는 잡지 못한다.
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2]).resolve()

FILE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
SHELL_TOOLS = {"Bash", "PowerShell"}

DENY_DIRS = {
    ("reports",): "reports/의 지표 JSON·CSV는 스크립트만 씁니다. regret이나 R² 같은 값을 손으로 고치지 마세요",
    ("models",): "models/의 학습 결과물은 학습 스크립트로만 다시 만듭니다",
    ("data", "datasets"): "data/datasets/의 데이터셋은 python -m data.generate로만 다시 만듭니다",
}
DENY_FILES = {}
ASK_DIRS = {
    ("physics",): ("physics/ 변경입니다. 물리 코드가 바뀌면 생성한 데이터와 학습 모델이 모두 무효가 됩니다"
                   "(헌법 원칙 I). 정말 바꿀지 확인하세요"),
}

RECURSIVE_DELETE = re.compile(
    r"""(?ix)
    (^|[\s;&|(`])rm\s+(?:[^;&|\n]*\s)?(?:-[^\s]*[rR][^\s]*|--recursive)\b      # rm -rf, rm -fr, rm -R, rm --recursive
    | (^|[\s;&|(`])(?:Remove-Item|ri|rmdir|rd|del|erase)\b[^;&|\n]*\s-r(?:e(?:c(?:u(?:r(?:s(?:e)?)?)?)?)?)?\b   # Remove-Item ... -Recurse (줄임 포함)
    | (^|[\s;&|(`])(?:rmdir|rd)\s+/s\b                                          # cmd rmdir /s
    | shutil\.rmtree\b                                                           # python -c "shutil.rmtree(...)"
    """
)


def _decide(decision, reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": f"[훅] {reason}",
        }
    }, ensure_ascii=False))
    return 0


def _rel_parts(raw: str):
    """프로젝트 루트 기준 상대 경로 조각(소문자). 프로젝트 밖이면 None."""
    p = Path(raw)
    if not p.is_absolute():
        p = ROOT / p
    p = os.path.normcase(os.path.abspath(p))
    root = os.path.normcase(str(ROOT))
    try:
        rel = Path(p).relative_to(root)
    except ValueError:
        return None
    return tuple(part.lower() for part in rel.parts)


def check_file(raw: str):
    if not raw:
        return None
    rel = _rel_parts(raw)
    if not rel:
        return None
    for prefix, reason in DENY_DIRS.items():
        if rel[:len(prefix)] == prefix and len(rel) > len(prefix):
            return "deny", f"{reason}: {raw}"
    if rel in DENY_FILES:
        return "deny", f"{DENY_FILES[rel]}: {raw}"
    for prefix, reason in ASK_DIRS.items():
        if rel[:len(prefix)] == prefix and len(rel) > len(prefix):
            return "ask", f"{reason}: {raw}"
    return None


# ---------------------------------------------------------------- 셸 명령의 physics/ 쓰기 감지

PHYSICS_DIR = os.path.normcase(str(ROOT / "physics"))
SEPARATORS = {";", "&&", "||", "|", "&", "\n"}
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?\n[ \t]*\2[ \t]*(?=\n|$)", re.S)
HERESTRING = re.compile(r"@(['\"])\r?\n.*?\r?\n\1@", re.S)
TOKEN = re.compile(r'"(?:[^"\\]|\\.)*"|\'[^\']*\'|&&|\|\||[;|&\n]|\d*>>?|[^\s;|&>]+')   # x>file 도 분리
REDIRECT = re.compile(r"^\d*>>?(.*)$")
FD_DUP = re.compile(r"\d*>&\d+")

PY_WRITES = [   # 경로 리터럴은 따옴표를 넘지 않게 [^'"]+ 로 제한
    re.compile(r"""open\(\s*(['"])([^'"]+)\1\s*,\s*(?:mode\s*=\s*)?['"][^'"]*[wax+]"""),       # open('p','w')
    re.compile(r"""Path\(\s*(['"])([^'"]+)\1\s*\)\s*\.\s*(?:write_text|write_bytes|unlink|touch|rename|replace)\b"""),
    re.compile(r"""shutil\.(?:copy\w*|move)\(\s*(?:['"][^'"]+['"]|\w+)\s*,\s*(['"])([^'"]+)\1"""),   # 대상(두 번째 인자)
    re.compile(r"""os\.(?:remove|unlink|rename|replace)\(\s*(['"])([^'"]+)\1"""),
    re.compile(r"""os\.(?:rename|replace)\(\s*(?:['"][^'"]+['"]|\w+)\s*,\s*(['"])([^'"]+)\1"""),
]

ALL_ARG_WRITERS = {"tee", "truncate", "set-content", "add-content", "out-file", "clear-content",
                   "new-item", "sc", "ac", "ni", "rm", "del", "erase", "remove-item", "ri", "unlink", "touch"}
COPY_MOVE = {"cp", "mv", "copy", "move", "copy-item", "move-item", "cpi", "mi", "cpp", "install", "rsync"}
INPLACE = {"sed", "perl", "gsed"}
GIT_WRITE_SUBCMDS = {"checkout", "restore", "apply", "mv", "rm"}


def _unquote(t: str) -> str:
    return t[1:-1] if len(t) >= 2 and t[0] == t[-1] and t[0] in "'\"" else t


def _under_physics(tok: str, cwd: str) -> bool:
    t = _unquote(tok.strip())
    if not t or any(c in t for c in "$%~`") or t.startswith("-"):
        return False
    t = re.sub(r"^/([a-zA-Z])/", r"\1:/", t)                   # Git Bash 경로 /c/work → C:/work
    g = re.search(r"[*?\[]", t)
    if g:
        t = t[:g.start()] or "."
    p = Path(t)
    if not p.is_absolute():
        p = Path(cwd) / p
    p = os.path.normcase(os.path.abspath(p))
    return p == PHYSICS_DIR or p.startswith(PHYSICS_DIR + os.sep)


def _segments(cmd: str):
    seg = []
    for tok in TOKEN.findall(FD_DUP.sub(" ", cmd)):
        if tok in SEPARATORS:
            if seg:
                yield seg
            seg = []
        else:
            seg.append(tok)
    if seg:
        yield seg


def _write_targets(seg):
    targets, words = [], []
    i = 0
    while i < len(seg):                                         # 리다이렉트 대상 분리
        m = REDIRECT.match(seg[i])
        if m and not seg[i].startswith(("'", '"')):
            if m.group(1):
                targets.append(m.group(1))
            elif i + 1 < len(seg):
                targets.append(seg[i + 1])
                i += 1
        else:
            words.append(seg[i])
        i += 1
    while words and (re.match(r"^\w+=", words[0]) or words[0].lower() in {"sudo", "command", "&", "."}):
        words = words[1:]                                       # VAR=x cmd, sudo cmd
    if not words:
        return targets
    name = re.sub(r"\.exe$", "", os.path.basename(_unquote(words[0]).replace("\\", "/"))).lower()
    args = words[1:]
    plain = [a for a in args if not a.startswith("-")]

    if name in INPLACE and any(a.startswith("-") and not a.startswith("--") and "i" in a[1:] or a.startswith("--in-place")
                               for a in args):
        targets += plain
    elif name in ALL_ARG_WRITERS:
        targets += plain
    elif name in COPY_MOVE:
        dest = None
        for j, a in enumerate(args):
            low = a.lower()
            if (low.startswith("-dest") or low == "-t") and j + 1 < len(args):
                dest = args[j + 1]
            elif low.startswith("--target-directory="):
                dest = a.split("=", 1)[1]
        if dest is None and len(plain) >= 2:
            dest = plain[-1]
        if dest:
            targets.append(dest)
    elif name == "dd":
        targets += [a[3:] for a in args if a.startswith("of=")]
    elif name == "git" and plain and plain[0] in GIT_WRITE_SUBCMDS:
        targets += plain[1:]
    return targets


def shell_writes_physics(cmd: str, cwd: str):
    """physics/ 아래로 쓰는 대상이 있으면 그 대상 문자열을, 없으면 None."""
    for rx in PY_WRITES:                                        # python 코드(heredoc 포함)의 쓰기
        for m in rx.finditer(cmd):
            if _under_physics(m.group(2), cwd):
                return m.group(2)
    shell_text = HERESTRING.sub(" ", HEREDOC.sub(" ", cmd))     # heredoc 본문은 셸 명령이 아님
    for seg in _segments(shell_text):
        for t in _write_targets(seg):
            if _under_physics(t, cwd):
                return _unquote(t)
    return None


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        event = json.loads(sys.stdin.buffer.read().decode("utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        # 보호 장치가 입력을 못 읽었을 때 조용히 통과시키지 않는다(fail-closed).
        print(f"[훅] guard_protected.py가 입력을 해석하지 못해 차단합니다: {e}", file=sys.stderr)
        return 2
    tool = event.get("tool_name", "")
    ti = event.get("tool_input") or {}

    if tool in FILE_TOOLS:
        res = check_file(ti.get("file_path") or ti.get("notebook_path") or "")
        if res:
            return _decide(*res)
    elif tool in SHELL_TOOLS:
        cmd = ti.get("command", "")
        if RECURSIVE_DELETE.search(cmd):
            return _decide("deny", "재귀 삭제 명령은 막혀 있습니다(models/, data/ 일괄 삭제 방지). "
                                   f"꼭 필요하면 사용자에게 직접 실행을 요청하세요: {cmd[:200]}")
        target = shell_writes_physics(cmd, event.get("cwd") or str(ROOT))
        if target:
            return _decide("ask", f"{ASK_DIRS[('physics',)]} (셸 명령이 {target}에 씁니다)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
