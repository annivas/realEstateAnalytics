"""
Scheduled data collection using APScheduler.
"""
import logging
import signal
import sys
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import COLLECTION_SCHEDULE, MONITORED_AREAS
from database.models import init_db
from collector.api_client import SpitogatosClient

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class CollectionScheduler:
    """Scheduler for automated data collection."""

    def __init__(self):
        self.scheduler = BlockingScheduler()
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        """Setup graceful shutdown handlers."""
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

    def _shutdown(self, signum, frame):
        """Gracefully shutdown the scheduler."""
        logger.info("Shutdown signal received, stopping scheduler...")
        self.scheduler.shutdown(wait=False)

    def collection_job(self):
        """Job function to run data collection."""
        logger.info("=" * 60)
        logger.info("Starting scheduled data collection...")
        logger.info("=" * 60)
        
        try:
            # Ensure database exists
            init_db()
            
            with SpitogatosClient() as client:
                run = client.collect_and_store()
            
            logger.info(
                f"Collection completed: {run.properties_found} properties found, "
                f"{run.new_properties} new, {run.updated_properties} updated, "
                f"{run.price_changes_detected} price changes"
            )
            
        except Exception as e:
            logger.error(f"Collection job failed: {e}", exc_info=True)

    def start(
        self,
        hour: int = None,
        minute: int = None,
        day_of_week: str = None,
        run_immediately: bool = False,
    ):
        """
        Start the scheduler with configured collection times.
        
        Args:
            hour: Hour to run (0-23). Defaults to config value.
            minute: Minute to run (0-59). Defaults to config value.
            day_of_week: Days to run ('*' for all, 'mon-fri' for weekdays).
            run_immediately: If True, run collection immediately on start.
        """
        # Use config defaults if not specified
        hour = hour if hour is not None else COLLECTION_SCHEDULE["hour"]
        minute = minute if minute is not None else COLLECTION_SCHEDULE["minute"]
        day_of_week = day_of_week or COLLECTION_SCHEDULE["day_of_week"]
        
        # Create cron trigger
        trigger = CronTrigger(
            hour=hour,
            minute=minute,
            day_of_week=day_of_week,
        )
        
        # Add the collection job
        self.scheduler.add_job(
            self.collection_job,
            trigger=trigger,
            id="data_collection",
            name="Real Estate Data Collection",
            replace_existing=True,
        )
        
        logger.info(f"Scheduler configured to run at {hour:02d}:{minute:02d}")
        logger.info(f"Days: {day_of_week}")
        logger.info(f"Monitoring {len(MONITORED_AREAS)} areas: {list(MONITORED_AREAS.values())}")
        
        # Run immediately if requested
        if run_immediately:
            logger.info("Running initial collection...")
            self.collection_job()
        
        # Start scheduler
        logger.info("Starting scheduler. Press Ctrl+C to stop.")
        try:
            self.scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler stopped.")


def main():
    """Run the scheduler from command line."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Real Estate Data Collection Scheduler")
    parser.add_argument(
        "--hour",
        type=int,
        default=None,
        help=f"Hour to run collection (0-23). Default: {COLLECTION_SCHEDULE['hour']}",
    )
    parser.add_argument(
        "--minute",
        type=int,
        default=None,
        help=f"Minute to run collection (0-59). Default: {COLLECTION_SCHEDULE['minute']}",
    )
    parser.add_argument(
        "--days",
        type=str,
        default=None,
        help="Days to run ('*' for all, 'mon-fri' for weekdays). Default: '*'",
    )
    parser.add_argument(
        "--run-now",
        action="store_true",
        help="Run collection immediately on start",
    )
    
    args = parser.parse_args()
    
    # Initialize database
    init_db()
    
    # Start scheduler
    scheduler = CollectionScheduler()
    scheduler.start(
        hour=args.hour,
        minute=args.minute,
        day_of_week=args.days,
        run_immediately=args.run_now,
    )


if __name__ == "__main__":
    main()
