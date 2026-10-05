"""Independent audit: join schedules by source primary names, never by aliases."""

import argparse
import gzip
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from lxml import etree


def name_key(value):
    return "".join(value.casefold().split())


def text(element):
    return " ".join("".join(element.itertext()).split())


def first_title(element):
    titles = element.findall("title")
    preferred = next((t for t in titles if t.get("lang") == "pl"), None)
    return text(preferred if preferred is not None else titles[0]) if titles else ""


def timestamp(value):
    return datetime.strptime(value, "%Y%m%d%H%M%S %z").astimezone(UTC).isoformat()


def read_schedule(path):
    names = {}
    aliases = defaultdict(set)
    slots = defaultdict(set)
    live_slots = defaultdict(set)
    with open(path, "rb") as header:
        compressed = header.read(2) == b"\x1f\x8b"
    opener = gzip.open if compressed else open
    with opener(path, "rb") as handle:
        for _, element in etree.iterparse(
            handle,
            events=("end",),
            tag=("channel", "programme"),
            resolve_entities=False,
            no_network=True,
            load_dtd=False,
        ):
            if element.tag == "channel":
                channel_id = element.get("id", "")
                displays = [text(item) for item in element.findall("display-name")]
                if displays:
                    names[channel_id] = displays[0]
                    for display in displays:
                        aliases[" ".join(display.casefold().split())].add(channel_id)
            else:
                start, stop = element.get("start"), element.get("stop")
                if start and stop:
                    try:
                        channel_id = element.get("channel", "")
                        slot = (timestamp(start), timestamp(stop), first_title(element))
                        slots[channel_id].add(slot)
                        if element.find("live") is not None:
                            live_slots[channel_id].add(slot)
                    except ValueError:
                        pass
            element.clear()
            while element.getprevious() is not None:
                del element.getparent()[0]
    return names, aliases, slots, live_slots


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("epg", type=Path)
    parser.add_argument("sources", type=Path, nargs="+")
    parser.add_argument("--allow-live-channel", action="append", default=[])
    args = parser.parse_args()
    expected = defaultdict(set)
    for path in args.sources:
        names, _, schedules, _ = read_schedule(path)
        for channel_id, slots in schedules.items():
            if channel_id in names:
                expected[name_key(names[channel_id])].update(slots)
    names, aliases, schedules, live_slots = read_schedule(args.epg)
    collisions = {name: sorted(ids) for name, ids in aliases.items() if len(ids) > 1}
    mismatches = []
    checked_channels = []
    unchecked_channels = []
    checked_programmes = 0
    live_override_programmes_skipped = 0
    for channel_id, name in names.items():
        slots = schedules.get(channel_id, set())
        if not slots:
            continue
        expected_slots = expected.get(name_key(name))
        if not expected_slots:
            unchecked_channels.append({"id": channel_id, "name": name, "programmes": len(slots)})
            continue
        checked_channels.append(channel_id)
        checked_programmes += len(slots)
        for slot in sorted(slots - expected_slots):
            if channel_id in args.allow_live_channel and slot in live_slots[channel_id]:
                live_override_programmes_skipped += 1
                continue
            mismatches.append({"id": channel_id, "name": name, "slot": slot})
    now = datetime.now(UTC).isoformat()
    sample_ids = [
        "polsat.pl",
        "polsat-1.pl",
        "polsat-sport-1.pl",
        "polsat-sport-2.pl",
        "tvn.pl",
        "tvn-7.pl",
        "tvn-24.pl",
        "tvn-turbo.pl",
        "tvp-1.pl",
        "tvp-2.pl",
        "axn.pl",
        "axn-black.pl",
        "axn-white.pl",
        "axn-spin.pl",
        "animal-planet.pl",
        "eleven-sports-1.pl",
        "eleven-sports-2.pl",
        "eurosport-1.pl",
        "eurosport-2.pl",
    ]
    samples = {}
    for channel_id in sample_ids:
        slots = sorted(schedules.get(channel_id, set()))
        upcoming = [slot for slot in slots if slot[1] > now]
        samples[channel_id] = {
            "name": names.get(channel_id),
            "programmes": len(slots),
            "now_and_next": upcoming[:3],
        }
    report = {
        "audited_at": now,
        "epg": str(args.epg),
        "channel_count": len(names),
        "programme_count": sum(map(len, schedules.values())),
        "duplicate_display_names": collisions,
        "channels_checked_against_source_primary_names": len(checked_channels),
        "programmes_checked_against_source_primary_names": checked_programmes,
        "source_identity_mismatch_count": len(mismatches),
        "source_identity_mismatches_by_channel": dict(Counter(item["id"] for item in mismatches)),
        "live_override_programmes_skipped": live_override_programmes_skipped,
        "source_identity_mismatches": mismatches[:40],
        "channels_without_exact_primary_name_reference": unchecked_channels,
        "sample_schedules": samples,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(bool(collisions or mismatches))


if __name__ == "__main__":
    raise SystemExit(main())
