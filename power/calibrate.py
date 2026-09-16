#!/usr/bin/env python3
"""Teach the cup-count estimator real brew sizes.

Each calibration point is (brew duration in seconds, cups). plot.estimate_cups
fits a line through these points (or scales linearly for a single point) and
brew_summary() reports an estimated cup count for a brew's duration.

Usage:
  python3 calibrate.py list                     recent brews per device
  python3 calibrate.py add <device> <cups>      teach: last brew of <device> made <cups> cups
  python3 calibrate.py add <device> <cups> --at HH:MM   pick a specific brew by its end time
  python3 calibrate.py show                     current calibration and fitted mapping
  python3 calibrate.py remove <idx>             drop calibration point #idx (see show)
  python3 calibrate.py reset                    clear all calibration points

Example:
  brew 8 cups on the 'oikea' plug, then:
      python3 calibrate.py add oikea 8
  Repeat for a different batch size (e.g. 6 cups), then
      python3 calibrate.py show
"""

import argparse
import sys
from datetime import timedelta

import plot
from config import DEFAULT_DEVICE, DEVICES


def _brews_for(device):
    if device not in DEVICES:
        sys.exit(f"Unknown device '{device}'. Available: {', '.join(DEVICES)}")
    return plot.detect_brews(device)


def cmd_list(args):
    for device in DEVICES:
        brews = _brews_for(device)
        if not brews:
            print(f"{device}: no brews detected")
            continue
        for i, b in list(enumerate(brews))[-8:]:
            start = b["start"].strftime("%Y-%m-%d %H:%M")
            end = b["end"].strftime("%H:%M")
            duration = plot.fmt_duration(b["duration"])
            print(f"[{i}] {device}: {start}–{end} · {duration}")
        print()


def cmd_add(args):
    brews = _brews_for(args.device)
    if not brews:
        sys.exit(f"No brews detected for '{args.device}' — brew a pot first.")
    if args.at:
        matches = [b for b in brews if b["end"].strftime("%H:%M") == args.at]
        if not matches:
            sys.exit(f"No brew ending at {args.at} for '{args.device}'.")
        brew = matches[-1]
    else:
        brew = brews[-1]
    secs = brew["duration"].total_seconds()
    if secs <= 0:
        sys.exit("Brew duration is not usable for calibration.")
    cups = args.cups
    if cups <= 0:
        sys.exit("Cups must be a positive number.")

    points = plot.load_calibration()
    points = [(s, c) for s, c in points if round(s) != round(secs)]
    points.append((secs, cups))
    path = plot.save_calibration(points)

    estimated = plot.estimate_cups(timedelta(seconds=secs))
    print(
        f"Taught: {args.device} brew of {plot.fmt_duration(timedelta(seconds=secs))}"
        f" ({secs:.0f} s) = {cups:.1f} cups."
    )
    print(f"Fit estimate at {secs:.0f} s: {estimated:.1f} cups.")
    print(f"Saved to {path}")


def cmd_show(args):
    points = plot.load_calibration()
    if not points:
        print("No calibration points yet.")
        print("Teach one:  python3 calibrate.py add <device> <cups>")
        return
    print(f"{len(points)} calibration point(s):")
    for idx, (secs, cups) in enumerate(points):
        print(f"  [{idx}] {plot.fmt_duration(timedelta(seconds=secs)):>8} ({secs:5.0f} s) -> {cups:.1f} cups")
    print("\nFitted estimates for common brew durations:")
    for secs in (180, 240, 300, 360, 420):
        if not points:
            break
        estimate = plot.estimate_cups(timedelta(seconds=secs))
        if estimate is None:
            continue
        print(f"  {plot.fmt_duration(timedelta(seconds=secs)):>8} (~{secs:3.0f} s) -> ~{estimate:4.1f} cups")


def cmd_remove(args):
    points = plot.load_calibration()
    if args.idx >= len(points):
        sys.exit(f"No point #{args.idx} (have {len(points)} points). Use 'show' to list them.")
    removed = points.pop(args.idx)
    plot.save_calibration(points)
    print(f"Removed [{args.idx}] {removed[0]:.0f} s -> {removed[1]:.1f} cups")


def cmd_reset(args):
    plot.save_calibration([])
    print("Calibration cleared.")


def main():
    parser = argparse.ArgumentParser(description="Teach brew sizes to the cup-count estimator.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="recent brews per device")
    p_list.set_defaults(func=cmd_list)

    p_add = sub.add_parser("add", help="teach the last brew of a device as <cups>")
    p_add.add_argument("device", type=str.lower)
    p_add.add_argument("cups", type=float)
    p_add.add_argument("--at", metavar="HH:MM", help="pick the brew ending at this time, not the last")
    p_add.set_defaults(func=cmd_add)

    p_show = sub.add_parser("show", help="show calibration points and fitted mapping")
    p_show.set_defaults(func=cmd_show)

    p_remove = sub.add_parser("remove", help="remove calibration point by index")
    p_remove.add_argument("idx", type=int)
    p_remove.set_defaults(func=cmd_remove)

    p_reset = sub.add_parser("reset", help="clear all calibration points")
    p_reset.set_defaults(func=cmd_reset)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()