"""Automated playtest bot - AI player that plays the game."""

import argparse
import asyncio

import structlog

logger = structlog.get_logger()


async def run_playtest(template: str, turns: int) -> dict:
    """Run an automated playtest session.

    The bot generates player actions and feeds them through the full
    game engine pipeline, logging results for quality analysis.
    """
    logger.info("playtest_start", template=template, turns=turns)

    results = {
        "template": template,
        "total_turns": turns,
        "completed_turns": 0,
        "errors": [],
        "narration_lengths": [],
        "dice_rolls": 0,
    }

    # TODO: Initialize a test campaign and iterate turns
    logger.info("playtest_complete", results=results)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SAGA Playtest Bot")
    parser.add_argument("--turns", type=int, default=100)
    parser.add_argument("--template", type=str, default="tutorial")
    args = parser.parse_args()

    asyncio.run(run_playtest(args.template, args.turns))
