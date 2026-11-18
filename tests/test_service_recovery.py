#!/usr/bin/env python3
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

"""Exercise recovery signals against real processes in an isolated PID namespace."""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("bwrap"), "requires isolated process namespace")
class RecoveryTests(unittest.TestCase):
    def test_pause_is_conditional_owned_and_reversible(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            shutil.copy(ROOT / "src/diagnostics/runtime/recovery.sh", base / "recovery.sh")
            subprocess.run(
                ["cc", "-x", "c", "-", "-o", str(base / "sleeper")],
                input="#include <unistd.h>\nint main(void){for(;;)pause();}\n",
                text=True,
                check=True,
                capture_output=True,
            )
            (base / "exercise.py").write_text(r"""
import os, pathlib, shutil, signal, subprocess, time
r=pathlib.Path('/tmp/dextend-service');r.mkdir()
s=pathlib.Path('/etc/yamaha-sdl/usb-v1');s.mkdir(parents=True)
(s.parent/'enabled').touch()
(s/'active').write_text('none')
(s/'status').write_text('ROLLED_BACK_RESTART_REQUIRED')
shutil.copy('/work/recovery.sh',r/'recovery.sh')
(r/'debug-api').write_text('#!/bin/sh\ntest -f /tmp/card\n')
(r/'debug-api').chmod(0o700)
(r/'diagnostics.sh').write_text('#!/bin/sh\nexit 0\n')
shutil.copy('/bin/busybox','/usr/sbin/pidof')
for name in ['ARMadb-driver','ARMHiCar','unrelated','receiver-native']:
    shutil.copy('/work/sleeper','/usr/sbin/'+name)
pathlib.Path('/tmp/bin').mkdir()
pathlib.Path('/script').mkdir()
pathlib.Path('/script/phone_link_deamon.sh').write_text('while :; do sleep 1; done\n')
shutil.copy('/usr/sbin/ARMHiCar','/tmp/bin/ARMHiCar')
procs=[]
def spawn(path):
    p=subprocess.Popen([path,'120']);procs.append(p);return p
adb=spawn('/usr/sbin/ARMadb-driver')
hicar=spawn('/tmp/bin/ARMHiCar')
other=spawn('/usr/sbin/unrelated')
launcher=subprocess.Popen(['ash','/script/phone_link_deamon.sh','HiCar','start'],executable='/bin/busybox');procs.append(launcher)
wrong_launcher=subprocess.Popen(['ash','/script/phone_link_deamon.sh','CarPlay','start'],executable='/bin/busybox');procs.append(wrong_launcher)
shutil.copy('/usr/sbin/ARMadb-driver','/tmp/bin/ARMadb-driver')
with open('/tmp/bin/ARMadb-driver','ab') as f:f.write(b'changed')
wrong_binary=spawn('/tmp/bin/ARMadb-driver')
foreign=spawn('/usr/sbin/ARMadb-driver');os.kill(foreign.pid,signal.SIGSTOP)
owner=spawn('/bin/sleep')
def stamp(p):return pathlib.Path('/proc/'+str(p.pid)+'/stat').read_text().rsplit(') ',1)[1].split()[19]
def stopped(p):return pathlib.Path('/proc/'+str(p.pid)+'/stat').read_text().rsplit(') ',1)[1].split()[0]=='T'
def wait(pred):
    until=time.monotonic()+5
    while time.monotonic()<until:
        if pred():return
        time.sleep(.03)
    raise AssertionError('condition timed out')
def guard(start=None):
    p=subprocess.Popen(['sh',str(r/'recovery.sh'),str(owner.pid),start or stamp(owner)]);procs.append(p);return p
# Reused PID cannot be resumed from an old journal.
(r/'recovery.paused').write_text(str(foreign.pid)+' 0\n')
g=guard()
time.sleep(1.2)
assert not stopped(adb) and not stopped(hicar) and stopped(foreign)
# Card alone is insufficient when a native release is selected.
(s/'active').write_text('a'*64)
pathlib.Path('/tmp/card').touch()
time.sleep(1.2);assert not stopped(adb)
(s/'active').write_text('none')
native=spawn('/usr/sbin/receiver-native')
time.sleep(1.2);assert not stopped(adb), subprocess.run(['sh','-c','command -v pidof; pidof receiver-native; cat /proc/'+str(native.pid)+'/comm; cat /tmp/dextend-service/recovery-status'],capture_output=True,text=True).stdout
native.kill();native.wait()
wait(lambda: stopped(adb) and stopped(hicar))
wait(lambda: stopped(launcher))
assert not stopped(other) and stopped(foreign) and not stopped(wrong_launcher) and not stopped(wrong_binary)
late=spawn('/usr/sbin/ARMadb-driver');wait(lambda: stopped(late))
# External-card removal returns all processes that this guard owns.
pathlib.Path('/tmp/card').unlink()
wait(lambda:not stopped(adb) and not stopped(hicar) and not stopped(late) and not stopped(launcher))
assert stopped(foreign)
# Return to a selected native release also releases ownership.
pathlib.Path('/tmp/card').touch();wait(lambda: stopped(adb))
(s/'active').write_text('b'*64);wait(lambda:not stopped(adb))
(s/'active').write_text('none');wait(lambda: stopped(adb))
# Manager crash cannot leave the factory paused indefinitely.
owner.kill();owner.wait();g.wait(timeout=5)
assert not stopped(adb) and not stopped(hicar) and stopped(foreign)
owner=spawn('/bin/sleep');g=guard();wait(lambda: stopped(adb))
# Interrupted guard: next guard reclaims its journal and cleans up on stop.
g.kill();g.wait();g=guard();wait(lambda:stopped(adb))
time.sleep(.2);g.terminate();g.wait(timeout=5)
assert not stopped(adb) and not stopped(hicar) and stopped(foreign)
# Forced guard termination during service shutdown still has a synchronous undo.
g=guard();wait(lambda:stopped(adb));g.kill();g.wait()
subprocess.run(['sh',str(r/'recovery.sh'),'release'],check=True,timeout=5)
assert not stopped(adb) and not stopped(hicar) and stopped(foreign)
# A stale owner identity must never pause anyone.
g=guard('0');g.wait(timeout=5);assert not stopped(adb)
for p in procs:
    if p.poll() is None:p.kill()
    p.wait()
""")
            run = subprocess.run(
                [
                    "bwrap",
                    "--tmpfs",
                    "/",
                    "--ro-bind",
                    "/usr",
                    "/usr",
                    "--tmpfs",
                    "/usr/sbin",
                    "--symlink",
                    "usr/bin",
                    "/bin",
                    "--symlink",
                    "usr/lib",
                    "/lib",
                    "--symlink",
                    "usr/lib64",
                    "/lib64",
                    "--ro-bind",
                    "/etc/alternatives",
                    "/etc/alternatives",
                    "--dev",
                    "/dev",
                    "--unshare-pid",
                    "--proc",
                    "/proc",
                    "--unshare-net",
                    "--die-with-parent",
                    "--dir",
                    "/tmp",
                    "--bind",
                    str(base),
                    "/work",
                    sys.executable,
                    "/work/exercise.py",
                ],
                capture_output=True,
                text=True,
                timeout=40,
            )
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()
