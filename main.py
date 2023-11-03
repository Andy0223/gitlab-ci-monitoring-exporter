import asyncio
import logging
from datetime import datetime, timezone
import sys
import os
from flask import Flask, Response
from retry import retry
from prometheus.exporter import PrometheusExporter, generate_latest
from gitlabApi.gitlab import GitlabApiInteraction

# Create Flask App
app = Flask(__name__)
# Create logger
log_format = "%(asctime)s.%(msecs)03dZ [%(levelname)s] %(message)s"
logging.basicConfig(
    stream=sys.stdout, level=logging.INFO, format=log_format, datefmt="%Y-%m-%dT%H:%M:%S"
)
logger = logging.getLogger(__name__)
# Create Prometheus Exporter
exporter = PrometheusExporter()
# Create gitlab api interaction class
gitlab_api_interaction = GitlabApiInteraction()
group_id = os.environ.get("GROUP_ID")
last_fetch_time = None

logger.info("Process initialized")


# Metrics Define and Initialized
def init_metrics():
    # pipeline level
    exporter.add_gauge_metric(
        "gitlab_pipeline_duration_seconds",
        "Duration of GitLab pipeline in seconds",
        ["group_id", "path_with_namespace", "pipeline_id", "source", "ref", "status"],
    )
    exporter.add_gauge_metric(
        "gitlab_pipeline_queued_duration_seconds",
        "Queued duration of GitLab pipeline in seconds",
        ["group_id", "path_with_namespace", "pipeline_id", "source", "ref", "status"],
    )
    exporter.add_counter_metric(
        "gitlab_pipeline_executed_counts",
        "Executed counts of GitLab pipeline",
        ["group_id", "path_with_namespace", "pipeline_id", "source", "ref", "status"],
    )
    # job level
    exporter.add_gauge_metric(
        "gitlab_job_duration_seconds",
        "Duration of GitLab job in seconds",
        [
            "group_id",
            "runner_description",
            "job_id",
            "job_name",
            "path_with_namespace",
            "source",
            "pipeline_id",
            "ref",
            "status",
        ],
    )
    exporter.add_gauge_metric(
        "gitlab_job_queued_duration_seconds",
        "Queued duration of GitLab job in seconds",
        [
            "group_id",
            "runner_description",
            "job_id",
            "job_name",
            "path_with_namespace",
            "source",
            "pipeline_id",
            "ref",
            "status",
        ],
    )
    exporter.add_counter_metric(
        "gitlab_job_executed_counts",
        "Executed counts of GitLab job",
        [
            "group_id",
            "runner_description",
            "job_id",
            "job_name",
            "path_with_namespace",
            "source",
            "pipeline_id",
            "ref",
            "status",
        ],
    )

# Fetch pipelines for all projects in specific group
@retry(exceptions=Exception, tries=3, delay=1, backoff=2)
async def fetch_project_pipelines(start_time, end_time):
    try:
        all_pipelines = {}
        projects = await gitlab_api_interaction.get_subgroup_projects(group_id)
        pipelines = await gitlab_api_interaction.select_pipelines_for_execution(
            projects, start_time, end_time
        )
        if pipelines is not None:
            all_pipelines.update(pipelines)
        else:
            logger.info("No pipelines to update")
        return all_pipelines
    except Exception as e:
        logger.error(f"Error occurred: {e}")


# Fetch Jobs for all runber manager in specific group
@retry(exceptions=Exception, tries=3, delay=1, backoff=2)
async def fetch_runner_jobs(start_time, end_time):
    try:
        jobs = await gitlab_api_interaction.select_jobs_for_execution(
            group_id, start_time, end_time
        )

        return jobs
    except Exception as e:
        logger.error(f"Error occurred: {e}")


# insert metrics to default registry
async def collect_metrics(records, record_type):
    if not records:
        logger.info(f"No {record_type} to collect")
        return
    for _, record_attr in records.items():
        try:
            record_attr["duration"] = record_attr["duration"]
            record_attr["queued_duration"] = record_attr["queued_duration"]
            labels = record_attr.copy()
            del labels["duration"]
            del labels["queued_duration"]
            exporter.set_metric(
                f"gitlab_{record_type}_duration_seconds",
                labels,
                record_attr["duration"],
            )
            exporter.set_metric(
                f"gitlab_{record_type}_queued_duration_seconds",
                labels,
                record_attr["queued_duration"],
            )
            exporter.increment_metric(f"gitlab_{record_type}_executed_counts", labels)
        except Exception as e:
            logger.error(f"Error occurred: {e}")


@app.route("/", methods=["GET"])
def index():
    return "Ok", 200


@app.route("/metrics", methods=["GET"])
def expose_metrics():
    try:
        metrics_data = generate_latest()
        response = Response(metrics_data, mimetype="text/plain")
        exporter.clear_metrics()
        return response
    except Exception as e:
        error_message = f"Error occurred while exposing metrics: {e}"
        logger.error(error_message)


async def start_fetch():
    while True:
        global last_fetch_time

        if last_fetch_time is None:
            start_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            start_time = datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%S.%fZ")
        else:
            start_time = last_fetch_time
        logger.info("start_time: %s", start_time)

        end_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        end_time = datetime.strptime(end_time, "%Y-%m-%dT%H:%M:%S.%fZ")
        logger.info(f"end_time: {end_time}")

        last_fetch_time = end_time
        # fetch pipelines and jobs
        pipelines = await fetch_project_pipelines(start_time, end_time)
        jobs = await fetch_runner_jobs(start_time, end_time)
        # collect jobs and pipelines metrics
        await collect_metrics(pipelines, "pipeline")
        await collect_metrics(jobs, "job")
        # reset gitlab class after finishing one fetch
        gitlab_api_interaction.reset_init()

@retry(exceptions=Exception, tries=3, delay=1, backoff=2)
def run_application():    
    try:
        loop = asyncio.get_event_loop()
        asyncio_task = loop.create_task(start_fetch())
        app_task = loop.run_in_executor(None, app.run, "0.0.0.0", 8000)
        loop.run_until_complete(asyncio.gather(asyncio_task, app_task))
    except Exception as e:
        logging.error(f"Error occurred: {e}")


if __name__ == "__main__":
    init_metrics()
    run_application()
