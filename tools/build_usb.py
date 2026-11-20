#!/usr/bin/env python3
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

"""Build three offline, profile-restricted A15W laboratory USB packages.

No network, device access or deployment. Input is an explicit development
package from package.py. Every image is decoded and inspected before delivery.
"""

import argparse
import io
import json
import lzma
from pathlib import Path
import re
import subprocess
import tarfile
import zipfile

from usb_image import MAX_IMAGE, decode, encode, sha

ROOT = Path(__file__).resolve().parents[1]
MAX_RUNTIME = 1024 * 1024
QUALIFIED_AOA_MODULES = {
    "18adac8ec65cb1efec71917dc85c038a072e52689ee271b107b46e3699c45690",  # 0.32-alpha
    "199637ce89e0662c654e423dc0c67b0feb7be7de35a0b868ee3a986a5d41d97f",  # 0.33-alpha
}
# Base installation/JFFS2 reserve plus fixed radio-state overhead.
# The device adds ceil(3 * current/original radio-config bytes / 1024).
FLASH_RESERVE_KIB = 352


def read(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Not a regular file: {path.name}")
    return path.read_bytes()


def verify_runtime(payload, version):
    decoder = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE, memlimit=8 * 1024 * 1024)
    raw = decoder.decompress(payload, max_length=MAX_RUNTIME + 1)
    if len(raw) > MAX_RUNTIME or not decoder.eof or decoder.unused_data:
        raise ValueError("Runtime LZMA bounds/trailing data failure")
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        files = {}
        for member in archive:
            if (
                not member.isfile()
                or member.name in files
                or member.name.startswith("/")
                or ".." in Path(member.name).parts
                or not re.fullmatch(r"[A-Za-z0-9_./-]+", member.name)
            ):
                raise ValueError("Unsafe runtime member")
            files[member.name] = archive.extractfile(member).read()
    manifest = json.loads(files["manifest.json"])
    if manifest["version"] != version or files.get("waiting-version") != (version + "\n").encode():
        raise ValueError("Runtime and waiting screen versions must match the IMG version")
    members = manifest["members"]
    if set(files) != set(members) | {"manifest.json", "SHA256SUMS"}:
        raise ValueError("Unlisted or missing runtime members")
    for name, digest in members.items():
        if sha(files[name]) != digest:
            raise ValueError("Runtime manifest mismatch")
    # The on-device checker uses this list. Require full coverage, including the manifest.
    checks = "".join(
        f"{sha(data)}  {name}\n" for name, data in sorted(files.items()) if name != "SHA256SUMS"
    ).encode()
    if files["SHA256SUMS"] != checks:
        raise ValueError("Runtime checksum list differs from the archive contents")
    expected_restore = {"restore/" + name: data for name, data in restore_inputs(version).items()}
    packed_restore = {name: data for name, data in files.items() if name.startswith("restore/")}
    if packed_restore != expected_restore:
        raise ValueError("Runtime must contain the restore procedure built for this version")
    for name in (
        "yamaha-sdl-live",
        "receiver-native",
        "iphone-usb-role",
        "bluetooth-autoconnect",
        "phone-policy",
        "yamaha_aoa.ko",
    ):
        data = files[name]
        if data[:6] != b"\x7fELF\x01\x01" or data[18:20] != b"\x28\x00":
            raise ValueError("Expected ARM32 little-endian ELF")
    if sha(files["yamaha_aoa.ko"]) not in QUALIFIED_AOA_MODULES:
        raise ValueError("Module is outside the qualified laboratory ABI profile")
    return manifest, len(raw)


def render(template, replacements):
    for name, value in replacements.items():
        template = template.replace(("@" + name + "@").encode(), str(value).encode())
    if re.search(rb"@[A-Z_]+@", template):
        raise ValueError("Unexpanded template")
    return template


def release_sequence(version, sequence, previous=None):
    lab = re.fullmatch(r"(20[0-9]{2})\.([01][0-9])\.([0-3][0-9])-usb-lab([1-9][0-9]{0,3})", version)
    release = re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-alpha|-beta)?", version)
    if lab and sequence is None:
        sequence = int("".join(lab.groups()[:3])) * 10000 + int(lab.group(4))
    elif release:
        if sequence is None and previous is not None:
            sequence = max(previous + 1, 202611140005)
        if sequence is None or not 202611140004 < sequence <= 999999999999:
            raise ValueError("Specify a valid updater sequence or supply the previous IMG")
    else:
        raise ValueError("Use YYYY.MM.DD-usb-labN or a release version without a v prefix")
    if previous is not None and sequence <= previous:
        raise ValueError("Updater sequence must be higher than the previous IMG sequence")
    return sequence


def sequence_from_image(image):
    members = decode(read(image))
    data, _ = members.get("tmp/dextend/release/version.txt", (b"", 0))
    if not re.fullmatch(rb"[A-Za-z0-9._-]+\n[1-9][0-9]{0,11}\n", data):
        raise ValueError("Previous IMG does not contain a valid updater sequence")
    return int(data.splitlines()[1])


def installer_entry(checks, mode, version):
    worker_sha = next(
        line.split()[0] for line in checks.decode().splitlines() if line.endswith("  transaction.sh")
    )
    return f"""#!/bin/sh
set -eu
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
cd /tmp/update/tmp/dextend
bundle_error() {{
    umask 077
    mkdir /tmp/dextend-usb-lock 2>/dev/null || exit 1
    trap 'rmdir /tmp/dextend-usb-lock' EXIT
    usb=/mnt/UPAN
    target=$usb/DEXTEND-RESULT.txt
    [ -d "$usb" ] && [ ! -L /mnt ] && [ ! -L "$usb" ] && [ ! -L "$target" ] || exit 1
    [ ! -e "$target" ] || [ -f "$target" ] || exit 1
    grep -q ' /mnt/UPAN vfat rw' /proc/mounts || exit 1
    if [ -f "$target" ] && grep -q '^DEXTEND USB' "$target"; then
        archive=$(mktemp -d "$usb/dextend-log.XXXXXX") || exit 1
        cp "$target" "$archive/DEXTEND-RESULT.txt" && sync || exit 1
    fi
    stage=$(mktemp "$usb/.dextend-result.XXXXXX") || exit 1
    trap 'rm -f "$stage"; rmdir /tmp/dextend-usb-lock' EXIT
    printf 'DEXTEND USB v2\\noperation={mode}\\nversion={version}\\nresult=REJECTED\\ndetail=%s\\nwrite_started=0\\n' "$1" >"$stage"
    printf 'step=verify_installer status=failed\\n' >>"$stage"
    if [ "$1" = DAMAGED_BUNDLE ]; then
        while read -r expected path; do
            actual=missing_or_unreadable
            if [ -f "$path" ] && [ ! -L "$path" ]; then
                actual=$(sha256sum "$path" | awk '{{print $1}}')
            fi
            [ "$actual" = "$expected" ] || printf 'mismatch=%s expected=%s actual=%s\\n' "$path" "$expected" "$actual" >>"$stage"
        done < BUNDLE.sha256
    fi
    mv "$stage" "$target"
    sync
    exit 1
}}
# The verified worker records progress while checking the rest of the package.
if [ ! -f transaction.sh ] || [ -L transaction.sh ] || [ "$(sha256sum transaction.sh | awk '{{print $1}}')" != {worker_sha} ]; then
    [ -f BUNDLE.sha256 ] && [ ! -L BUNDLE.sha256 ] && [ "$(sha256sum BUNDLE.sha256 | awk '{{print $1}}')" = {sha(checks)} ] || bundle_error DAMAGED_BUNDLE_MANIFEST
    bundle_error DAMAGED_BUNDLE
fi
sh ./transaction.sh usb-bundle {sha(checks)}
# The OEM success path deletes /etc/module_version after finish.sh.
# Our transaction already installed/restored and verified every persistent file.
# Stop that path explicitly, keeping factory metadata untouched.
if [ -e /etc/module_version ]; then
    sh ./transaction.sh finish 0 preserve-metadata
    exit 1
fi
# The transaction has verified its persistent copy. Do not let the OEM checker
# count the consumed runtime archives again against the remaining flash space.
# Keep the small finish worker and profile until the OEM calls finish.sh.
if ! rm -rf ./release; then
    sh ./transaction.sh finish 1
    exit 1
fi
""".encode()


def installer_inputs():
    profile = json.loads(read(ROOT / "src/usb/profile.json"))
    boot = read(ROOT / "src/usb/boot.sh")
    profiles = [profile, *profile.get("additional_profiles", [])]
    for item in profiles:
        if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){3}", item["software_version"]):
            raise ValueError("Invalid OEM software version")
        if set(item["oem_files"]) != set(profile["oem_files"]) or not all(
            re.fullmatch(r"[0-9a-f]{64}", value) for value in item["oem_files"].values()
        ):
            raise ValueError("OEM profiles must specify the same complete file set")
    hook = (
        """#!/bin/sh
# Dextend USB v1 entry point; the OEM main service must continue immediately.
set -eu
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
s=/etc/yamaha-sdl/usb-v1
[ ! -L /etc/yamaha-sdl ] && [ -d "$s" ] && [ ! -L "$s" ] || exit 1
[ -f /etc/yamaha-sdl/enabled ] || exit 0
[ -f "$s/boot.sh" ] && [ ! -L "$s/boot.sh" ] || exit 1
[ "$(sha256sum "$s/boot.sh" | awk '{print $1}')" = BOOT_HASH ] || exit 1
cd /
sh "$s/boot.sh" >/dev/null 2>&1 </dev/null &
exit 0
""".replace("BOOT_HASH", sha(boot))
    ).encode()
    constants = {
        "restore_0_22_sidecar_sha": profile["restore_0_22_sidecar_sha256"],
        "stock_rcs": profile["stock_rcs_sha256"],
        "ssh_rcs": profile["repaired_ssh_rcs_sha256"],
        "legacy_hook": profile["legacy_hook_sha256"],
        "hook_sha": sha(hook),
        "boot_sha": sha(boot),
        "beta1_hook_sha": profile["beta1_hook_sha256"],
        "beta1_boot_sha": profile["beta1_boot_sha256"],
        "beta1_restore_sha": profile["beta1_restore_sha256"],
        "v033_hook_sha": profile["usb_v1_0_33_hook_sha256"],
        "v033_boot_sha": profile["usb_v1_0_33_boot_sha256"],
        "recent_hook_sha": profile["recent_usb_v1_hook_sha256"],
        "recent_boot_sha": profile["recent_usb_v1_boot_sha256"],
        "previous_hook_sha": profile["previous_usb_v1_hook_sha256"],
        "previous_boot_sha": profile["previous_usb_v1_boot_sha256"],
        "older_hook_sha": profile["older_usb_v1_hook_sha256"],
        "older_boot_sha": profile["older_usb_v1_boot_sha256"],
        "format_sha": sha(b"dextend-usb-v1\n"),
        "empty_sha": sha(b""),
    }
    constants["additional_oem_profiles"] = (
        "'"
        + "|".join(
            item["software_version"]
            + "@"
            + ";".join(f"{v}  {k}" for k, v in item["oem_files"].items())
            for item in profile.get("additional_profiles", [])
        )
        + "'"
    )
    profile_sh = "".join(f"{k}={v}\n" for k, v in constants.items()).encode()
    common = {
        "profile.sh": profile_sh,
        "profile.json": (json.dumps(profile, indent=2) + "\n").encode(),
        "OEM.sha256": "".join(f"{v}  {k}\n" for k, v in profile["oem_files"].items()).encode(),
        "LEGACY.sha256": "".join(
            f"{v}  {k}\n" for k, v in profile["legacy_files"].items()
        ).encode(),
        "boot.sh": boot,
        "hook.sh": hook,
        "format": b"dextend-usb-v1\n",
        "empty": b"",
        "LICENSE": read(ROOT / "LICENSE"),
        "NOTICE": read(ROOT / "NOTICE"),
    }
    return common


def restore_inputs(version):
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,16}", version):
        raise ValueError("Invalid version for the restore worker")
    common = installer_inputs()
    files = {name: common[name] for name in ("profile.sh", "OEM.sha256", "LEGACY.sha256", "format")}
    files["update-protocol"] = b"2\n"
    files["service-key-restore.sh"] = read(ROOT / "src/diagnostics/runtime/borrow-key.sh")
    files.update({n: read(ROOT / "src/usb" / n) for n in ("radio-names.sh", "radio-config.awk")})
    files["transaction.sh"] = render(
        read(ROOT / "src/usb/transaction.sh.in"),
        {"MODE": "restore-oem", "RELEASE": "", "VERSION": version, "SEQUENCE": 0},
    )
    return files


def make_bundle(package, output, version, sequence=None, previous_img=None):
    previous = sequence_from_image(previous_img) if previous_img is not None else None
    sequence = release_sequence(version, sequence, previous)
    if output.exists() or output.is_symlink():
        raise ValueError("Output must be a new directory")
    runtime = read(package / "native-runtime.tar.lzma")
    manifest, unpacked = verify_runtime(runtime, version)
    service = (
        read(package / "service-runtime.tar.lzma")
        if (package / "service-runtime.tar.lzma").exists()
        else None
    )
    if service is not None:
        from service_package import verify_service

        service_unpacked = verify_service(service, version)
    flash_required_kib = (len(runtime) + len(service or b"") + 1023) // 1024 + FLASH_RESERVE_KIB
    native = read(package / "native-boot.sh")
    expected = read(ROOT / "packaging/native-boot.sh.in").replace(
        b"@RUNTIME_SHA256@", sha(runtime).encode()
    )
    if native != expected:
        raise ValueError("Unexpected native boot coordinator")
    # Preserve the coordinator's runtime paths and behavior; select only its
    # persistent payload directory. The installer never executes this program.
    native = native.replace(b"state=$root/etc/yamaha-sdl\n", b"state=${DEXTEND_RELEASE_DIR:?}\n", 1)
    release_files = {
        "native-boot.sh": native,
        "native-runtime.tar.lzma": runtime,
        "version.txt": (version + "\n" + str(sequence) + "\n").encode(),
    }
    if service is not None:
        release_files["service-runtime.tar.lzma"] = service
        release_files["service-boot.sh"] = read(ROOT / "src/runtime/start-service.sh")
    sums = "".join(f"{sha(v)}  {n}\n" for n, v in sorted(release_files.items())).encode()
    release_id = sha(sums)
    release_files["SHA256SUMS"] = sums
    common = installer_inputs()
    profile = json.loads(common["profile.json"])
    images = {}
    for mode in ("probe", "install", "restore-oem"):
        files = dict(common)
        files["service-key-restore.sh"] = read(ROOT / "src/diagnostics/runtime/borrow-key.sh")
        files.update(
            {n: read(ROOT / "src/usb" / n) for n in ("radio-names.sh", "radio-config.awk")}
        )
        files["transaction.sh"] = render(
            read(ROOT / "src/usb/transaction.sh.in"),
            {"MODE": mode, "RELEASE": release_id, "VERSION": version, "SEQUENCE": sequence},
        )
        if mode == "install":
            files.update({"release/" + n: v for n, v in release_files.items()})
        entries = {
            f"tmp/dextend/{n}": (v, 0o700 if n.endswith(".sh") else 0o600) for n, v in files.items()
        }
        checks = "".join(f"{sha(v)}  {n}\n" for n, v in sorted(files.items())).encode()
        entries["tmp/dextend/BUNDLE.sha256"] = (checks, 0o600)
        once = installer_entry(checks, mode, version)
        entries["tmp/once.sh"] = (once, 0o755)
        entries["tmp/finish.sh"] = (
            b'#!/bin/sh\nexec sh /tmp/update/tmp/dextend/transaction.sh finish "${1:-1}"\n',
            0o755,
        )
        for name, (data, _) in entries.items():
            if name.endswith(".sh"):
                subprocess.run(["sh", "-n"], input=data, check=True, capture_output=True)
                subprocess.run(
                    ["busybox", "ash", "-n"], input=data, check=True, capture_output=True
                )
        image = encode(entries)
        decoded = decode(image)
        info = {
            "operation": mode,
            "version": version,
            "release_id": release_id,
            "image_sha256": sha(image),
            "profile": profile["name"] if mode == "probe" else profile["product"],
            "sequence": sequence,
            "install_strategy": "restore-oem-then-install-fresh" if mode == "install" else None,
            "hardware_validation": "not performed; laboratory candidate",
            "runtime_manifest": manifest if mode == "install" else None,
            "runtime_unpacked_bytes": unpacked if mode == "install" else 0,
            "members": {
                n: {"sha256": sha(v), "mode": oct(m), "bytes": len(v)}
                for n, (v, m) in decoded.items()
            },
        }
        if mode == "install":
            info["size_budget"] = {
                "image_bytes": len(image),
                "image_codec_limit_bytes": MAX_IMAGE,
                "runtime_compressed_bytes": len(runtime),
                "service_compressed_bytes": len(service or b""),
                "service_unpacked_bytes": service_unpacked if service is not None else 0,
                "service_unpacked_limit_bytes": 4 * 1024 * 1024,
                "runtime_unpacked_limit_bytes": MAX_RUNTIME,
                "runtime_unpacked_headroom_bytes": MAX_RUNTIME - unpacked,
                "install_minimum_free_flash_kib": flash_required_kib,
                "additional_radio_flash": "ceil(3 * sum(max(current, original) file bytes) / 1024) KiB",
            }
        images[mode] = (image, info)
    output.mkdir(parents=True)
    for mode, (image, info) in images.items():
        directory = output / mode
        directory.mkdir()
        (directory / "A15W_Update.img").write_bytes(image)
        (directory / "SHA256SUMS").write_text(f"{sha(image)}  A15W_Update.img\n")
        (directory / "MANIFEST.json").write_text(json.dumps(info, indent=2) + "\n")
        (directory / "INSTRUKCJA.txt").write_text(instructions(mode, version))
        with zipfile.ZipFile(
            output / f"dextend-{mode}-{version}.zip", "w", zipfile.ZIP_DEFLATED
        ) as archive:
            for path in sorted(directory.iterdir()):
                archive.write(path, path.name)
    (output / "SHA256SUMS").write_text(
        "".join(f"{sha(read(p))}  {p.name}\n" for p in sorted(output.glob("*.zip")))
    )
    return {mode: info["image_sha256"] for mode, (_, info) in images.items()}


def instructions(mode, version):
    purposes = {
        "probe": "Próba przyjęcia obrazu i raport zgodności. Bez zapisu flash; zapisuje tylko RAM i wynik na pendrivie.",
        "install": "Pierwsza instalacja na A15W. Aktualizacja wycofuje najpierw rozpoznaną instalację Dextend, a potem instaluje nową od zera. Ustawienia dodatku zostaną usunięte.",
        "restore-oem": "Usunięcie rozpoznanego Dextend USB v1 lub native-clean rc2 i znanych narzędzi wifi-usb. Zachowuje skrypt rcS właściciela. Zachowuje konta, ustawienia, parowania i identyfikatory; nie jest kasowaniem ustawień użytkownika.",
    }
    return f"""DEXTEND {version} / {mode}
Kandydat laboratoryjny; testy na urządzeniu nie zostały wykonane dla tego obrazu.
{purposes[mode]}

Adapter: A15W. Wersja firmware, architektura i kernel są zapisywane w raporcie.
Paczka probe jest opcjonalna. Instalacja sprawdza integralność plików dodatku.
Przed install/restore-oem zachowaj sprawdzoną kopię obecnego urządzenia.
Na pendrivie FAT32 umieść tylko JEDEN obraz, jako A15W_Update.img w katalogu głównym.
Nie kopiuj wszystkich trzech obrazów naraz. Sprawdź SHA256SUMS przed użyciem.
Zasil dongla stabilnym zasilaczem USB poza motocyklem; po starcie włóż pendrive.
Podczas zapisu nie wyjmuj nośnika ani nie odłączaj zasilania.
Na pendrivie DEXTEND-RESULT.txt zawiera wynik oraz chronologiczny przebieg każdej rozpoczętej fazy instalatora.
Poprzedni raport jest zachowywany w osobnym katalogu dextend-log.*. FILES_COMMITTED oznacza, że updater jeszcze pracuje.
PREPARED_FOR_BOOT / OEM_RESTORED_RESTART_REQUIRED oznacza sprawdzony zapis.
Jeżeli istnieje module_version, detail=EXPECTED_OEM_ERROR_METADATA_PRESERVED_POWER_CYCLE
oznacza celowe zatrzymanie OEM po zapisie, aby zachować metadane. W tym jednym
przypadku komunikat błędu OEM jest oczekiwany; kieruj się wynikiem Dextend.
Zaczekaj również na zakończenie sygnalizacji OEM i dodatkowe 4 minuty zgodnie
z instrukcją nośnika CCPA, potem odłącz zasilanie, wyjmij pendrive i uruchom dongla.
Czas i LED tej nowej paczki wymagają próby sprzętowej; sam kolor nie dowodzi sukcesu.

Probe oraz ALREADY_INSTALLED celowo kończą once.sh kodem błędu, aby zatrzymać
kopiowanie OEM. Komunikat błędu OEM jest wtedy spodziewany: sprawdź własny raport.
REJECTED oznacza odmowę; przeczytaj detail. ERROR_AFTER_WRITE lub UPDATER_ERROR_AFTER_COMMIT wymagają sprawdzenia
stanu i kopii przed ponowieniem. Nie zakładaj automatycznie cofnięcia zapisu.

Przed zapisem tworzy się na USB katalog dextend-backup.* z before.tar,
sumą i listą ścieżek. To kopia zmienianych plików, nie całego flash.
Nie publikuj jej. Brak miejsca lub konflikt na ścieżce zajmowanej przez dodatek powodują odmowę.
Instalacja nie zmienia bootloadera, kernela, danych radia ani danych egzemplarza.
Start zdrowych procesów nie zastępuje sprawdzenia obrazu, sterowania i audio.
Powrót OEM przestaje uruchamiać serwis przy następnym starcie; bieżące procesy
kończą się przy świadomym cyklu zasilania po zakończeniu updatera.
"""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--sequence", type=int)
    parser.add_argument(
        "--previous-img",
        type=Path,
        help="Use the previous IMG to select or check the updater sequence",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            make_bundle(args.package, args.output, args.version, args.sequence, args.previous_img),
            indent=2,
        )
    )
