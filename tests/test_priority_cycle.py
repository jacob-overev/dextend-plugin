# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

"""Run the phone supervisor with an isolated radio, receiver processes and uptime."""

from pathlib import Path
import json
import shutil
import socket
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
IPHONE = "02:00:00:00:00:11"
ANDROID = "02:00:00:00:00:22"
SECOND_ANDROID = "02:00:00:00:00:33"
AAP = "ln -sf /dev/rfcomm1 /tmp/rfcomm_AAP"
IAP2 = "ln -sf /dev/rfcomm0 /tmp/rfcomm_IAP2"


def script(path, body):
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(0o700)


class PriorityCycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.build.cleanup)
        cls.policy = Path(cls.build.name) / "phone-policy"
        subprocess.run(["cc", "-O2", str(ROOT / "src/native/phone-policy.c"), "-o", cls.policy],
                       check=True)

    def replay(self, phones, steps, ticks, preference="carplay", timed=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = root / "tmp/yamaha-sdl"
            conf = root / "etc/yamaha-sdl"
            bonds = root / "tmp/bluetooth/02:00:00:00:AA:01"
            for path in [work, conf, bonds, root / "run", root / "bin", root / "sys"]:
                path.mkdir(parents=True)
            (conf / "enabled").touch()
            (conf / "phone-policy.json").write_text(json.dumps(
                dict(schema=1, preferred=preference, order=[peer for peer, _ in phones])))
            (bonds / "linkkeys").write_text("".join(f"{p} fixture\n" for p, _ in phones))
            (bonds.parent / "services").write_text("".join(f"{p} {s}\n" for p, s in phones))
            shutil.copy(ROOT / "src/runtime/supervise-auto.sh", work)
            shutil.copy(self.policy, work)
            script(work / "debug-log.sh", 'debug() { echo "$*" >>/tmp/events; echo "$(cat /tmp/tick) $*" >>/tmp/timed; }')
            script(work / "bluetooth-autoconnect", 'echo "bt $*" >>/tmp/events')
            script(work / "receiver-native", 'echo $$ >/tmp/aa-pid; exec /bin/sleep 300')
            script(work / "supervise-phone.sh", "exec /bin/sleep 300")
            for name in ["hciconfig", "killall"]:
                script(root / "bin" / name, "exit 0")
            (root / "bin/awk").symlink_to(Path(shutil.which("awk")).resolve())
            script(root / "bin/pidof", "echo 31")
            script(root / "bin/hcitool", 'if [ "$1" = dc ]; then echo "dc $2" >>/tmp/events; exit 0; fi\n'
                   'echo Connections:; cat /tmp/acl 2>/dev/null; exit 0')
            (root / "tmp/clock").write_text("100.00 0\n")
            (root / "tmp/node").touch()
            cases = "\n".join(f"{tick}) {action} ;;" for tick, action in steps.items())
            script(root / "bin/sleep", f"""
n=$(cat /tmp/tick 2>/dev/null || echo 0)
n=$((n+1))
echo "$n" >/tmp/tick
echo "$((100+n)).00 0" >/tmp/clock
[ ! -f phone-selection ] || head -1 phone-selection >phone-selected
case "$n" in
{cases}
esac
[ "$n" -lt {ticks} ] || rm -f /etc/yamaha-sdl/enabled
""")
            cmd = ["bwrap", "--die-with-parent", "--unshare-pid", "--unshare-net", "--ro-bind",
                   "/", "/", "--proc", "/proc", "--dev", "/dev"]
            for host, guest in [("tmp", "/tmp"), ("etc", "/etc"), ("sys", "/sys"),
                                ("run", "/run"), ("bin", "/opt"), ("tmp/clock", "/proc/uptime")]:
                cmd.extend(["--bind", str(root / host), guest])
            for i, peer in enumerate([IPHONE, ANDROID, SECOND_ANDROID]):
                tty = root / f"sys/class/tty/rfcomm{i}"
                tty.mkdir(parents=True)
                (tty / "address").write_text(peer.lower() + "\n")
                cmd.extend(["--bind", str(root / "tmp/node"), f"/dev/rfcomm{i}"])
            shell = ["/bin/sh", "./supervise-auto.sh"]
            if busybox := shutil.which("busybox"):
                # Some ash builds prefer built-in applets over PATH. Mock the
                # radio and clock explicitly and source the production script.
                mocks = ("sleep", "pidof", "killall", "hcitool", "hciconfig")
                functions = "".join(f'{name}() {{ /opt/{name} "$@"; }}\n' for name in mocks)
                shell = [busybox, "ash", "-c", functions + ". ./supervise-auto.sh"]
            with socket.socket(socket.AF_UNIX) as sock:
                sock.bind(str(root / "run/adb-driver"))
                subprocess.run(cmd + ["--setenv", "PATH", "/opt:/usr/bin:/bin", "--chdir",
                                      "/tmp/yamaha-sdl"] + shell,
                               check=True, timeout=90)
            return (root / ("tmp/timed" if timed else "tmp/events")).read_text().splitlines()

    def test_first_attempt_and_wrap_follow_platform_preference(self):
        phones = [(ANDROID, "AAP"), (IPHONE, "IAP2")]
        iphone = f"bt --connect {IPHONE} AUTO"
        android = f"bt --connect {ANDROID} AAP"
        for preference, order in [("carplay", [iphone, android]),
                                  ("android-auto", [android, iphone]),
                                  ("none", [android, iphone])]:
            with self.subTest(preference=preference):
                events = self.replay(phones, {}, 45, preference=preference)
                calls = [e for e in events if e.startswith("bt ") and e != "bt --listen"]
                self.assertEqual(calls[:4], order * 2)

    def test_empty_bonds_listens_until_a_phone_calls_or_bonds_are_restored(self):
        phones = [(IPHONE, "IAP2")]
        hide = "mv /tmp/bluetooth/*/linkkeys /tmp/bonds"
        restore = "mv /tmp/bonds /tmp/bluetooth/02:00:00:00:AA:01/linkkeys"
        events = self.replay(phones, {1: hide, 20: restore}, 34)
        self.assertIn("bt --listen", events)
        self.assertNotIn("bt ", events)
        self.assertEqual(events.count(f"bt --connect {IPHONE} AUTO"), 1)
        timed = self.replay(phones, {1: hide, 20: AAP, 24: "echo ready >phone-state"}, 32,
                            timed=True)
        self.assertFalse(any("priority_attempt" in e for e in timed))
        self.assertIn("20 priority_incoming service=AAP", timed)

    def test_delayed_profile_is_discovered_for_the_selected_bond(self):
        phones = [(IPHONE, "IAP2"), (ANDROID, "AAP")]
        events = self.replay(phones, {
            1: "mv /tmp/bluetooth/services /tmp/svc",
            12: "mv /tmp/svc /tmp/bluetooth/services",
        }, 35, preference="none")
        calls = [e for e in events if e.startswith("bt --connect")]
        self.assertEqual(calls, [f"bt --connect {IPHONE} AUTO",
                                 f"bt --connect {ANDROID} AAP",
                                 f"bt --connect {IPHONE} AUTO",
                                 f"bt --connect {ANDROID} AAP"])
        self.assertNotIn("bt ", events)

    def test_missing_profile_can_answer_on_android(self):
        events = self.replay([(ANDROID, "")], {7: AAP, 12: "echo ready >phone-state"}, 29)
        self.assertIn(f"bt --connect {ANDROID} AUTO", events)
        self.assertIn("STAGE AUTO_SELECT platform=aa-wireless", events)
        self.assertEqual(sum(e.startswith("bt --connect") for e in events), 1)

    def test_rejected_request_releases_turn_without_waiting_for_timeout(self):
        phones = [(IPHONE, "IAP2"), (ANDROID, "AAP")]
        events = self.replay(phones, {3: "echo 'exit 5' >>bluetooth-autoconnect"}, 18, timed=True)
        self.assertIn("5 priority_finished candidate=1 service=IAP2 reason=request_failed", events)
        self.assertIn("6 priority_attempt candidate=2 total=2 service=AAP", events)

    def test_wait_for_wifi_after_bluetooth_helper_ends(self):
        phones = [(IPHONE, "IAP2"), (ANDROID, "AAP")]
        ended = "cp priority-carplay priority-iap2-ended; cp priority-carplay priority-iap2-failed"
        events = self.replay(phones, {1: IAP2, 9: ended, 18: "touch iap2-wifi-request",
                                      22: "echo ready >phone-state"}, 60, timed=True)
        self.assertIn("9 priority_waiting_for_wifi", events)
        self.assertFalse(any("priority_finished" in e for e in events))
        events = self.replay(phones, {1: IAP2, 9: ended}, 28, timed=True)
        self.assertIn("24 priority_finished candidate=1 service=IAP2 reason=iap2_exit", events)
        self.assertIn("27 priority_attempt candidate=2 total=2 service=AAP", events)

    def test_unavailable_bluetooth_at_start_does_not_consume_first_turn(self):
        events = self.replay([(ANDROID, "AAP"), (IPHONE, "IAP2")], {
            1: "sed -i '2c exit 1' /opt/pidof; "
               "printf '#!/bin/sh\nexit 0\n' >/opt/bluetoothDaemon; chmod +x /opt/bluetoothDaemon",
            12: "sed -i '2c echo 31' /opt/pidof",
        }, 19, preference="android-auto", timed=True)
        self.assertEqual([e for e in events if "priority_attempt" in e],
                         ["12 priority_attempt candidate=1 total=2 service=AAP"])

    def test_listener_retries_after_failure_while_the_list_is_empty(self):
        events = self.replay([], {
            1: "echo 'test -e /tmp/radio-ready' >>bluetooth-autoconnect",
            4: "touch /tmp/radio-ready",
        }, 12, timed=True)
        self.assertIn("1 bluetooth_listen_failed exit=1", events)
        self.assertIn("6 bluetooth_listen_accepted", events)
        self.assertFalse(any("priority_attempt" in e for e in events))

    def test_lost_control_reply_allows_the_selected_phone_to_answer(self):
        phones = [(IPHONE, "IAP2"), (ANDROID, "AAP")]
        events = self.replay(phones, {3: "echo 'exit 6' >>bluetooth-autoconnect",
                                      8: IAP2, 12: "echo ready >phone-state"}, 24, timed=True)
        self.assertIn("8 priority_negotiating candidate=1 service=IAP2", events)
        self.assertFalse(any("priority_finished" in e for e in events))

    def test_fast_bluetooth_exit_and_link_removal_before_wifi(self):
        events = self.replay([(IPHONE, "IAP2")], {
            1: IAP2, 6: "cp priority-carplay priority-iap2-ended; rm /tmp/rfcomm_IAP2",
            18: "touch iap2-wifi-active", 22: "echo ready >phone-state",
        }, 35, timed=True)
        self.assertIn("6 priority_waiting_for_wifi", events)
        self.assertFalse(any("priority_finished" in e for e in events))

    def test_wired_phone_leaves_wireless_queue_at_the_top_on_unplug(self):
        phones = [(IPHONE, "IAP2"), (ANDROID, "AAP")]
        events = self.replay(phones, {
            1: "mkdir -p /sys/class/android_usb/android0; echo CONFIGURED >/sys/class/android_usb/android0/state",
            15: "rm /sys/class/android_usb/android0/state",
        }, 19, timed=True)
        self.assertEqual([e for e in events if "priority_attempt" in e],
                         ["15 priority_attempt candidate=1 total=2 service=IAP2"])

    def test_two_iphones_are_targeted_by_address_in_saved_order(self):
        phones = [(SECOND_ANDROID, "IAP2"), (IPHONE, "IAP2"), (ANDROID, "AAP")]
        events = self.replay(phones, {}, 39)
        self.assertEqual([e for e in events if e.startswith("bt --connect")],
                         [f"bt --connect {SECOND_ANDROID} AUTO", f"bt --connect {IPHONE} AUTO",
                          f"bt --connect {ANDROID} AAP", f"bt --connect {SECOND_ANDROID} AUTO"])

    def test_manual_pairing_pauses_dials_but_accepts_an_incoming_phone(self):
        events = self.replay([(IPHONE, "IAP2")], {2: "touch manual-pairing", 19: AAP,
                                                  23: "echo ready >phone-state"}, 30)
        self.assertFalse(any(e.startswith("bt --connect") for e in events))
        self.assertIn("priority_incoming service=AAP", events)

    def test_quiet_period_after_each_failure(self):
        events = self.replay([(IPHONE, "IAP2")], {}, 222, timed=True)
        calls = [int(line.split()[0]) for line in events if " priority_attempt " in line]
        ends = [int(line.split()[0]) for line in events if " priority_backoff " in line]
        delays = [int(line.split("seconds=")[1]) for line in events if " priority_backoff " in line]
        expected = [5, 10, 15, 20, 20, 30, 30]
        self.assertEqual(delays[:7], expected)
        self.assertEqual([start - end for start, end in zip(calls[1:8], ends)], expected)

    def test_iphone_initiates_during_cooldown_and_success_resets_delay(self):
        events = self.replay([(IPHONE, "IAP2")], {
            31: IAP2, 33: "echo ready >phone-state",
            38: "rm /tmp/rfcomm_IAP2; echo waiting >phone-state",
        }, 54, timed=True)
        self.assertIn("30 priority_backoff service=IAP2 failures=2 seconds=10", events)
        self.assertIn("31 priority_incoming service=IAP2", events)
        self.assertIn("31 priority_negotiating candidate=incoming service=IAP2", events)
        delays = [line.split("seconds=")[1] for line in events if " priority_backoff " in line]
        self.assertEqual(delays, ["5", "10", "5"])

    def test_incoming_android_during_unanswered_iphone_dial(self):
        events = self.replay([(IPHONE, "IAP2"), (ANDROID, "AAP")], {
            7: AAP, 11: "echo ready >phone-state", 15: IAP2,
        }, 30)
        self.assertIn("priority_incoming service=AAP", events)
        self.assertIn("STAGE AUTO_SELECT platform=aa-wireless", events)
        self.assertEqual(events.count(f"bt --connect {IPHONE} AUTO"), 1)
        self.assertNotIn("priority_incoming service=IAP2", events)

    def test_incoming_iphone_waits_for_android_negotiation(self):
        events = self.replay([(ANDROID, "AAP"), (IPHONE, "IAP2")], {
            1: AAP, 15: IAP2, 19: "touch phone-restart", 25: "echo ready >phone-state",
        }, 35, preference="android-auto")
        self.assertLess(events.index("priority_finished candidate=1 service=AAP reason=receiver_failed"),
                        events.index("priority_incoming service=IAP2"))

    def test_old_profile_cannot_bypass_cooldown_after_iap2_exit(self):
        events = self.replay([(IPHONE, "IAP2")], {
            1: IAP2, 8: "cp priority-carplay priority-iap2-failed",
        }, 20, timed=True)
        self.assertIn("8 priority_finished candidate=1 service=IAP2 reason=iap2_exit", events)
        self.assertEqual([int(line.split()[0]) for line in events if " priority_attempt " in line],
                         [5, 13])
        self.assertFalse(any(" priority_incoming " in line for line in events))

    def test_three_absent_phones_repeat_in_configured_order(self):
        phones = [(SECOND_ANDROID, "AAP"), (IPHONE, "IAP2"), (ANDROID, "AAP")]
        events = self.replay(phones, {}, 59)
        calls = [line.split()[2] for line in events if line.startswith("bt --connect ")]
        self.assertEqual(calls, [IPHONE, SECOND_ANDROID, ANDROID] * 2)

    def test_persistent_android_loses_turn_then_returning_iphone_connects(self):
        events = self.replay([(IPHONE, "IAP2"), (ANDROID, "AAP")], {
            1: AAP,
            3: f"echo '> ACL {ANDROID} handle 1' >/tmp/acl",
            68: IAP2,
            72: "echo ready >phone-state",
        }, 119)
        turns = [line.split()[-1] for line in events if line.startswith("priority_attempt ")]
        self.assertEqual(turns, ["service=IAP2", "service=AAP", "service=IAP2"])
        self.assertEqual(events.count(f"bt --connect {IPHONE} AUTO"), 2)
        self.assertIn("priority_negotiating candidate=1 service=IAP2", events)

    def test_receiver_exit_and_session_end(self):
        events = self.replay([(IPHONE, "IAP2"), (ANDROID, "AAP")], {
            1: AAP, 22: 'kill -PIPE "$(cat /tmp/aa-pid)"', 31: IAP2,
            34: "echo ready >phone-state", 60: "echo waiting >phone-state",
        }, 66)
        turns = [line.split()[-1] for line in events if line.startswith("priority_attempt ")]
        self.assertEqual(turns, ["service=IAP2", "service=AAP", "service=IAP2", "service=IAP2"])
        self.assertIn("auto_receiver_exit platform=aa-wireless exit=141", events)
        self.assertIn("priority_restart reason=session_ended", events)

    def test_failed_start_marker_advances_turn(self):
        events = self.replay([(IPHONE, "IAP2"), (ANDROID, "AAP")], {
            1: AAP, 21: "touch phone-restart",
        }, 33)
        self.assertIn("priority_finished candidate=2 service=AAP reason=receiver_failed", events)
        self.assertEqual(events.count(f"bt --connect {IPHONE} AUTO"), 2)
        self.assertEqual(events.count("auto_receiver_start platform=aa-wireless"), 1)

    def test_one_handset_exposing_two_profiles_has_one_turn(self):
        events = self.replay([(IPHONE, "IAP2"), (ANDROID, "AAP")], {
            1: "ln -sf /dev/rfcomm1 /tmp/rfcomm_IAP2; " + AAP,
        }, 20)
        self.assertEqual([event for event in events if event.startswith("priority_attempt")],
                         ["priority_attempt candidate=1 total=2 service=IAP2",
                          "priority_attempt candidate=2 total=2 service=AAP"])

    def test_matching_iphone_wakes_the_worker_once(self):
        inspect = 'if [ -f carplay-wakeup/pending ]; then echo woke >>/tmp/events; rm carplay-wakeup/pending; fi'
        events = self.replay([(IPHONE, "IAP2")], {7: inspect + "; " + IAP2, 8: inspect,
                                                 9: inspect, 10: "echo ready >phone-state"}, 16)
        self.assertEqual(events.count("woke"), 1)
        self.assertLess(events.index("priority_negotiating candidate=1 service=IAP2"),
                        events.index("woke"))

    def test_late_android_after_timeout_on_the_next_poll(self):
        phones = [(ANDROID, "AAP"), (IPHONE, "IAP2")]
        for iphone_replied in [False, True]:
            with self.subTest(iphone_replied=iphone_replied):
                steps = {16: AAP, 21: "echo ready >phone-state"}
                if iphone_replied:
                    steps[16] = IAP2 + "; " + AAP
                events = self.replay(phones, steps, 26, preference="android-auto", timed=True)
                self.assertIn("15 priority_finished candidate=1 service=AAP reason=timeout", events)
                self.assertIn("15 priority_attempt candidate=2 total=2 service=IAP2", events)
                if iphone_replied:
                    self.assertTrue(any("priority_negotiating candidate=2 service=IAP2" in e for e in events))
                    self.assertFalse(any("AUTO_SELECT platform=aa-wireless" in e for e in events))
                else:
                    self.assertIn("16 priority_incoming service=AAP", events)
                    self.assertTrue(any("AUTO_SELECT platform=aa-wireless" in e for e in events))

    def test_android_profile_after_ten_seconds_keeps_its_original_turn(self):
        phones = [(ANDROID, "AAP"), (IPHONE, "IAP2")]
        events = self.replay(phones, {
            14: f"echo '> ACL {ANDROID} handle 0' >/tmp/acl",
            15: IAP2, 16: AAP, 54: "echo ready >phone-state",
        }, 90, preference="android-auto", timed=True)
        self.assertIn("15 priority_waiting_for_android_profile candidate=1 seconds=5", events)
        self.assertTrue(any("priority_negotiating candidate=1 service=AAP" in e for e in events))
        self.assertEqual(sum("priority_attempt" in e for e in events), 1)
        self.assertFalse(any("priority_finished" in e or "priority_incoming" in e for e in events))

    def test_android_grace_expires_once_and_releases_the_next_phone(self):
        phones = [(ANDROID, "AAP"), (IPHONE, "IAP2")]
        steps = {8: f"echo '> ACL {ANDROID} handle 1' >/tmp/acl"}
        for incoming in [False, True]:
            with self.subTest(incoming=incoming):
                events = self.replay(phones, {**steps, **({17: IAP2} if incoming else {})},
                                     28, preference="android-auto", timed=True)
                self.assertEqual(sum("priority_waiting_for_android_profile" in e for e in events), 1)
                self.assertIn("20 priority_finished candidate=1 service=AAP reason=timeout", events)
                expected = ("21 priority_incoming service=IAP2" if incoming else
                            "20 priority_attempt candidate=2 total=2 service=IAP2")
                self.assertIn(expected, events)

    def test_android_gets_grace_on_a_retry_after_an_unanswered_first_attempt(self):
        events = self.replay([(ANDROID, "AAP")], {
            29: f"echo '> ACL {ANDROID} handle 2' >/tmp/acl",
            31: AAP, 38: "echo ready >phone-state",
        }, 48, preference="android-auto", timed=True)
        self.assertIn("15 priority_finished candidate=1 service=AAP reason=timeout", events)
        self.assertIn("20 priority_attempt candidate=1 total=1 service=AAP", events)
        self.assertIn("30 priority_waiting_for_android_profile candidate=1 seconds=5", events)
        self.assertTrue(any("priority_negotiating candidate=1 service=AAP" in e for e in events))
        self.assertEqual(sum("priority_finished" in e for e in events), 1)

    def test_stale_or_unrelated_acl_does_not_extend_android(self):
        phones = [(ANDROID, "AAP"), (IPHONE, "IAP2")]
        for tick, address in [(1, ANDROID), (12, SECOND_ANDROID)]:
            with self.subTest(address=address):
                events = self.replay(phones, {tick: f"echo '> ACL {address} handle 1' >/tmp/acl"},
                                     19, preference="android-auto", timed=True)
                self.assertFalse(any("priority_waiting_for_android_profile" in e for e in events))
                self.assertIn("15 priority_attempt candidate=2 total=2 service=IAP2", events)

    def test_active_session_survives_another_phone_and_resumes_queue_on_disconnect(self):
        phones = [(ANDROID, "AAP"), (IPHONE, "IAP2")]
        for pref, channel, other in [("android-auto", AAP, IAP2), ("carplay", IAP2, AAP)]:
            with self.subTest(pref=pref):
                events = self.replay(phones, {7: channel, 12: "echo ready >phone-state",
                                     20: other, 25: "rm /tmp/rfcomm_*", 30: "rm -f phone-state",
                                     34: "echo ready >phone-state", 80: "echo waiting >phone-state"},
                                     89, preference=pref, timed=True)
                self.assertFalse(any(12 <= int(e.split()[0]) < 80 and
                                     any(name in e for name in ["priority_", "bluetooth_connect",
                                         "bluetooth_listen", "AUTO_SELECT", "auto_receiver_start"])
                                     for e in events))
                self.assertTrue(any("priority_restart reason=session_ended" in e for e in events))
                self.assertTrue(any(int(e.split()[0]) >= 80 and "priority_attempt candidate=1" in e
                                    for e in events))

    def test_first_pairing_with_empty_list(self):
        events = self.replay([], {3: AAP, 12: "echo ready >phone-state"}, 25)
        self.assertIn("STAGE AUTO_SELECT platform=aa-wireless", events)
        self.assertFalse(any(event.startswith("bt --connect") for event in events))

    def test_android_preference_and_no_competing_attempts_while_ready(self):
        events = self.replay([(IPHONE, "IAP2"), (ANDROID, "AAP")], {
            1: AAP + "; " + IAP2, 12: "echo ready >phone-state",
        }, 65, preference="android-auto")
        self.assertEqual([line for line in events if line.startswith("priority_attempt ")],
                         ["priority_attempt candidate=1 total=2 service=AAP"])
        self.assertIn("STAGE AUTO_SELECT platform=aa-wireless", events)


if __name__ == "__main__":
    unittest.main()
