import json
from unittest.mock import Mock

from backend.hcc import remote_probe as probe


def test_docker_unavailable_is_explicit(monkeypatch):
    monkeypatch.setattr(probe, "run", lambda argv, **kwargs: (127, "", "command not installed"))
    result = probe.docker()
    assert result["available"] is False and "未安装" in result["error"]


def test_docker_and_systemd_normalization(monkeypatch):
    def command(argv, **kwargs):
        if argv[:2] == ["docker", "ps"]:
            return 0, json.dumps({"ID":"abc","Names":"web","Image":"nginx:stable","State":"running","Status":"Up 1 day","Ports":"80/tcp"}), ""
        if argv[:2] == ["docker", "stats"]:
            return 0, json.dumps({"Name":"web","CPUPerc":"1.2%","MemUsage":"32 MiB / 8 GiB"}), ""
        if argv[:2] == ["docker", "images"]:
            return 0, json.dumps({"Repository":"nginx","Tag":"stable"}), ""
        if argv[:2] == ["docker", "compose"]:
            return 0, json.dumps([{"Name":"web-stack","Status":"running(1)"}]), ""
        return 0, json.dumps([{"unit":"web.service","active":"failed","sub":"failed","load":"loaded","description":"Example"}]), ""
    monkeypatch.setattr(probe, "run", command)
    result = probe.docker()
    assert result["containers"][0]["cpu"] == "1.2%"
    assert result["compose"][0]["Name"] == "web-stack"
    assert probe.systemd()["services"][0]["active"] == "failed"


def test_git_paths_remain_argv_and_hooks_disabled(monkeypatch):
    commands = []
    def command(argv, **kwargs):
        commands.append(argv)
        if "branch" in argv: return 0,"main\n",""
        if "status" in argv: return 0," M file.txt\n",""
        if "log" in argv: return 0,"abc123\x1fupdate\x1f2 hours ago\n",""
        return 0,"0\t0\n",""
    monkeypatch.setattr(probe, "run", command)
    target = "/srv/repo; echo forbidden"
    result = probe.git_repo(target)
    assert result["dirty"] and result["changes"] == 1 and result["branch"] == "main"
    assert all(target in command for command in commands)
    assert all("core.fsmonitor=false" in command and "core.hooksPath=/dev/null" in command for command in commands)


def test_health_failure_is_bounded_and_explained(monkeypatch):
    opener = Mock()
    opener.open.side_effect = TimeoutError()
    monkeypatch.setattr(probe.urllib.request, "build_opener", lambda *args: opener)
    result = probe.health_check({"name":"agent","url":"http://127.0.0.1:8081/health"})
    assert result["status"] == "unhealthy" and result["code"] is None
    assert opener.open.call_args.kwargs["timeout"] == 3
