import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from app.schemas.campaign_export import CampaignExport
from app.services.export_validation import ExportIntegrityError, validate_campaign_export


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a campaign archive without database or provider access."
    )
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    try:
        archive = CampaignExport.model_validate_json(args.archive.read_bytes())
        validate_campaign_export(archive)
    except OSError:
        print("Campaign archive could not be read.", file=sys.stderr)
        return 1
    except (ValidationError, ExportIntegrityError):
        print("Campaign archive is invalid or contains inconsistent references.", file=sys.stderr)
        return 1
    print("Campaign archive is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
