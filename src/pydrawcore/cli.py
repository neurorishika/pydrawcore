from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from typing import Callable

from .controller import DrawCoreController
from .discovery import discover_devices


def _add_port_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--port", help="Serial port, for example COM4")


def _controller_from_args(args: argparse.Namespace) -> DrawCoreController:
    if args.port:
        return DrawCoreController.connect(args.port)
    return DrawCoreController.auto_connect()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pydrawcore")
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover = subparsers.add_parser("discover", help="List connected DrawCore devices")
    discover.set_defaults(handler=_cmd_discover)

    info = subparsers.add_parser("info", help="Read firmware, nickname, and status")
    _add_port_argument(info)
    info.set_defaults(handler=_cmd_info)

    pen_up = subparsers.add_parser("pen-up", help="Raise the pen")
    _add_port_argument(pen_up)
    pen_up.set_defaults(handler=_cmd_pen_up)

    pen_down = subparsers.add_parser("pen-down", help="Lower the pen")
    _add_port_argument(pen_down)
    pen_down.set_defaults(handler=_cmd_pen_down)

    move = subparsers.add_parser("move-relative", help="Move relative in physical units")
    _add_port_argument(move)
    move.add_argument("--x-mm", type=float, default=0.0)
    move.add_argument("--y-mm", type=float, default=0.0)
    move.add_argument("--feed-rate", type=int, default=1200, help="Native DrawCore feed rate")
    move.set_defaults(handler=_cmd_move)

    home = subparsers.add_parser("home", help="Run the native DrawCore homing command")
    _add_port_argument(home)
    home.set_defaults(handler=_cmd_home)

    raw_query = subparsers.add_parser("raw-query", help="Send a raw DrawCore query")
    _add_port_argument(raw_query)
    raw_query.add_argument("query")
    raw_query.set_defaults(handler=_cmd_raw_query)

    raw_command = subparsers.add_parser("raw-command", help="Send a raw DrawCore command")
    _add_port_argument(raw_command)
    raw_command.add_argument("command_text")
    raw_command.set_defaults(handler=_cmd_raw_command)

    return parser


def _cmd_discover(_args: argparse.Namespace) -> int:
    print(json.dumps([asdict(device) for device in discover_devices()], indent=2))
    return 0


def _cmd_info(args: argparse.Namespace) -> int:
    with _controller_from_args(args) as controller:
        print(json.dumps(asdict(controller.get_device_info()), indent=2))
    return 0


def _cmd_pen_up(args: argparse.Namespace) -> int:
    with _controller_from_args(args) as controller:
        controller.pen_up()
    return 0


def _cmd_pen_down(args: argparse.Namespace) -> int:
    with _controller_from_args(args) as controller:
        controller.pen_down()
    return 0


def _cmd_move(args: argparse.Namespace) -> int:
    with _controller_from_args(args) as controller:
        controller.move_relative(x_mm=args.x_mm, y_mm=args.y_mm, feed_rate=args.feed_rate)
    return 0


def _cmd_home(args: argparse.Namespace) -> int:
    with _controller_from_args(args) as controller:
        controller.home()
    return 0


def _cmd_raw_query(args: argparse.Namespace) -> int:
    with _controller_from_args(args) as controller:
        print(controller.raw_query(args.query).strip())
    return 0


def _cmd_raw_command(args: argparse.Namespace) -> int:
    with _controller_from_args(args) as controller:
        controller.raw_command(args.command_text)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler: Callable[[argparse.Namespace], int] = args.handler
    return handler(args)
