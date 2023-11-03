from datetime import datetime
import json
import random
import asyncio
import functools
import logging
import requests
import os
import sys
import time

# logger config
log_format = "%(asctime)s.%(msecs)03dZ [%(levelname)s] %(message)s"
logging.basicConfig(
    stream=sys.stdout, level=logging.INFO, format=log_format, datefmt="%Y-%m-%dT%H:%M:%S"
)
logger = logging.getLogger(__name__)
class GitlabApiInteraction:
    def __init__(self):
        # base URL
        self.GITLAB_API_URL = "https://gitlab.com/api/v4/"
        self.ignored_subgroup_path_list = os.environ.get('IGNORED_SUBGROUPS_PATH_LIST').split(',')
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        self.PRIVATE_TOKEN = self.select_private_token()
        self.unfinished_jobs = {}
        self.unfinished_pipelines = {}
        self.mapping_list = {}
        self.subgroups = []
        self.projects = []
    
    # Function to reset the class
    def reset_init(self):
        self.PRIVATE_TOKEN = self.select_private_token()
        self.mapping_list = {}
        self.subgroups = []
        self.projects = []
    
    # Function to select a private token from the list
    def select_private_token(self):
        retries = 3
        for _ in range(retries):
            token = self.get_random_token()
            if self.check_api_token_status(token):
                return token
            logger.warning("Token is not available")
        logger.error("All tokens are unavailable")
        raise Exception("All tokens are unavailable")

    # Function to get a random token from the list
    def get_random_token(self):
        PRIVATE_TOKENS = os.environ.get('PRIVATE_ACCESS_TOKEN')
        token_list = PRIVATE_TOKENS.split(',')
        random.shuffle(token_list)
        return token_list[0]

    # Function to check if the token is available
    def check_api_token_status(self, token):
        url = f"{self.GITLAB_API_URL}user"
        response = requests.get(url, headers={"PRIVATE-TOKEN": token})
        if response.status_code == 429:
            time.sleep(1)  # Add a delay to avoid hitting the rate limit too quickly
        elif response.status_code == 200:
            return True
        return False

    # Shared function for using asyncio to fetch items
    async def fetch_items_in_executor(self, function_to_run, *args):
        try:
            loop = asyncio.get_event_loop()
            # Use functools.partial to fix the args
            partial_function = functools.partial(function_to_run, *args)
            items = await loop.run_in_executor(None, partial_function)
            if not items:
                self.logger.info(f"{function_to_run.__name__} got empty response")
            else:
                return items
        except Exception as e:
            logger.error(f"Error occurred: {e}")

    # Function to get subgroups within a group
    def get_group_subgroups(self, group_id, page):
        per_page = 100
        url = f"{self.GITLAB_API_URL}groups/{group_id}/subgroups?per_page={per_page}&page={page}"
        response = requests.get(url, headers={"PRIVATE-TOKEN": self.PRIVATE_TOKEN})
        if response.status_code == 200:
            return response.json()
        else:
            response.raise_for_status()

    # Function to get projects within a group or subgroup
    def get_group_projects(self, group_id, page):
        per_page = 100
        url = f"{self.GITLAB_API_URL}groups/{group_id}/projects?per_page={per_page}&page={page}"
        response = requests.get(url, headers={"PRIVATE-TOKEN": self.PRIVATE_TOKEN})

        if response.status_code == 200:
            return response.json()
        else:
            response.raise_for_status()

    # Function to get runners within a group
    def get_group_runners(self, group_id):
        url = f"{self.GITLAB_API_URL}groups/{group_id}/runners"
        response = requests.get(url, headers={"PRIVATE-TOKEN": self.PRIVATE_TOKEN})

        if response.status_code == 200:
            return response.json()
        else:
            response.raise_for_status()

    # Function to recursively get subgroups and their projects
    async def get_subgroup_projects(self, group_id):
        project_page = 1
        subgroup_page = 1

        while True:
            # Fetch and add projects of the current group to self.projects
            projects = await self.fetch_items_in_executor(self.get_group_projects, group_id, project_page)

            if projects is not None:
                for project in projects:
                    project_name = project["path_with_namespace"]
                    project_id = project["id"]
                    self.mapping_list[project_id] = group_id
                    logger.info(f"Project: {project_id} / {project_name}")
                
                self.projects.extend(projects)
                
                if len(projects) <= 100:
                    break
                project_page += 1
            else:
                break

        while True:
            # Fetch and process subgroups
            subgroups = await self.fetch_items_in_executor(self.get_group_subgroups, group_id, subgroup_page)

            if subgroups is not None:
                for subgroup in subgroups:
                    subgroup_path = subgroup["full_path"]
                    if subgroup_path in self.ignored_subgroup_path_list:
                        continue
                    subgroup_id = subgroup["id"]
                    logger.info(f"Subgroup: {subgroup_path}")
                    # Recursively call get_subgroup_projects for subgroups
                    await self.get_subgroup_projects(subgroup_id)
                if len(subgroups) <= 100:
                    break
                subgroup_page += 1
            else:
                break

        return self.projects

    # Function to get pipelines within a project
    def get_projects_pipelines(self, project_id, page):
        per_page = 100  # show 100 results in a page
        url = f"{self.GITLAB_API_URL}projects/{project_id}/pipelines?per_page={per_page}&page={page}&order_by=id"
        response = requests.get(url, headers={"PRIVATE-TOKEN": self.PRIVATE_TOKEN})

        if response.status_code == 200:
            return response.json()
        else:
            response.raise_for_status()
            logger.warning(f"Error occurred: {response.status_code}")
            return None

    # Function to get pipelines' details within a project
    def get_pipeline_details(self, project_id, pipeline_id):
        url = f"{self.GITLAB_API_URL}projects/{project_id}/pipelines/{pipeline_id}"
        response = requests.get(url, headers={"PRIVATE-TOKEN": self.PRIVATE_TOKEN})

        if response.status_code == 200:
            return response.json()
        else:
            response.raise_for_status()

    # Function to select the pipelines within the time intervals
    async def select_pipelines_for_execution(self, projects, start_time, end_time):
        pipelines_for_all_projects = {}

        try:
            for project in projects:
                project_id = project["id"]
                project_path = project["path_with_namespace"]
                logger.info(f"ready to get pipeline for project: {project_path}")
                page = 1
                self.unfinished_pipelines.setdefault(project_id, list())
                traverse_count = 0
                unfinished_pipeline_length = len(self.unfinished_pipelines[project_id])
                current_unfinished_pipelines = list()
                pipelines_to_remove = list()

                while True:
                    logger.info(
                        f"{project_id}: {self.unfinished_pipelines[project_id]}"
                    )
                    pipelines = await self.fetch_items_in_executor(
                        self.get_projects_pipelines, project_id, page
                    )
        

                    # if no more pipelines, then break from loop
                    if not pipelines:
                        break

                    stop = False
                    for pipeline in pipelines:
                        if (
                            stop == True
                            and traverse_count == unfinished_pipeline_length
                        ):
                            break
                        pipeline_id = pipeline["id"]
                        pipeline = await self.fetch_items_in_executor(
                            self.get_pipeline_details, project_id, pipeline_id
                        )

                        if pipeline is None:
                            continue

                        for unfinished_pipeline_id in self.unfinished_pipelines[project_id]:
                            if pipeline_id == unfinished_pipeline_id:
                                traverse_count += 1
                                if pipeline["finished_at"] is not None:
                                    pipelines_to_remove.append(unfinished_pipeline_id)
                                    break
                            elif pipeline_id < unfinished_pipeline_id:
                                continue
                            else:
                                break

                        if pipeline["finished_at"] is None:
                            if pipeline_id not in self.unfinished_pipelines[project_id]:
                                current_unfinished_pipelines.append(pipeline_id)
                                pipeline_attr = {
                                    "group_id": self.mapping_list.get(project_id),
                                    "path_with_namespace": project_path,
                                    "source": pipeline["source"],
                                    "ref": pipeline["ref"],
                                    "pipeline_id": pipeline_id,
                                    "status": pipeline["status"],
                                    "duration": pipeline["duration"] or 0,
                                    "queued_duration": pipeline["queued_duration"] or 0,
                                }

                                pipelines_for_all_projects[pipeline_id] = pipeline_attr

                            continue

                        pipeline_finished_time = datetime.strptime(
                            pipeline["finished_at"], "%Y-%m-%dT%H:%M:%S.%fZ"
                        )
                        if pipeline_finished_time > end_time:
                            continue
                        elif pipeline_finished_time <= start_time:
                            stop = True
                            continue

                        pipeline_attr = {
                            "group_id": self.mapping_list.get(project_id),
                            "path_with_namespace": project_path,
                            "source": pipeline["source"],
                            "ref": pipeline["ref"],
                            "pipeline_id": pipeline_id,
                            "status": pipeline["status"],
                            "duration": pipeline["duration"] or 0,
                            "queued_duration": pipeline["queued_duration"] or 0,
                        }

                        pipelines_for_all_projects[pipeline_id] = pipeline_attr

                    if traverse_count == unfinished_pipeline_length:
                        break

                    page += 1

                for unfinished_pipeline_id in pipelines_to_remove:
                    self.unfinished_pipelines[project_id].remove(unfinished_pipeline_id)

                self.unfinished_pipelines[project_id].extend(
                    current_unfinished_pipelines
                )
                self.unfinished_pipelines[project_id].sort(reverse=True)

            logger.info(pipelines_for_all_projects)
            return pipelines_for_all_projects

        except Exception as e:
            logger.error(f"Error occurred while getting projects pipelines: {e}")

    # Function to get jobs and jobs' details within a runner in the group
    def get_runners_jobs(self, runner_id, page):
        per_page = 100  # show 100 results in a page
        url = f"{self.GITLAB_API_URL}runners/{runner_id}/jobs?per_page={per_page}&page={page}&order_by=id"
        response = requests.get(url, headers={"PRIVATE-TOKEN": self.PRIVATE_TOKEN})

        if response.status_code == 200:
            return response.json()
        else:
            response.raise_for_status()
            logger.warning(f"Error occurred: {response.status_code}")
            return None

    # Function to determine which jobs should collect in current execution
    async def select_jobs_for_execution(self, group_id, start_time, end_time):
        jobs_for_all_runners = {}

        try:
            runners = await self.fetch_items_in_executor(self.get_group_runners, group_id)
            for runner in runners:
                runner_id = runner["id"]
                logger.info(f"ready to get jobs for runner: {runner_id}")
                page = 1
                self.unfinished_jobs.setdefault(runner_id, list())
                traverse_count = 0
                unfinished_job_length = len(self.unfinished_jobs[runner_id])
                current_unfinished_jobs = list()
                jobs_to_remove = list()
                while True:
                    logger.info(f"{runner_id}: {self.unfinished_jobs[runner_id]}")
                    jobs = await self.fetch_items_in_executor(
                        self.get_runners_jobs, runner_id, page
                    )  
        
                    # if no more job, then break from while loop
                    if not jobs:
                        break

                    stop = False

                    for job in jobs:
                        if stop == True and traverse_count == unfinished_job_length:
                            break

                        job_id = job["id"]
                        job_finished_at = job["finished_at"]

                        for unfinished_job_id in self.unfinished_jobs[runner_id]:
                            if job_id > unfinished_job_id:
                                break
                            elif job_id < unfinished_job_id:
                                continue
                            else:
                                traverse_count += 1
                                if job_finished_at is not None:
                                    jobs_to_remove.append(unfinished_job_id)
                                    break

                        if job_finished_at is None:
                            if job_id not in self.unfinished_jobs[runner_id]:
                                current_unfinished_jobs.append(job_id)

                                job_attr = {
                                    "group_id": self.mapping_list.get(job["project"]["id"]),
                                    "runner_description": runner["description"],
                                    "job_id": job_id,
                                    "job_name": job["name"],
                                    "ref": job["ref"],
                                    "status": job["status"],
                                    "source": job['pipeline']['source'],
                                    "pipeline_id": job["pipeline"]["id"],
                                    "path_with_namespace": job["project"]["path_with_namespace"],
                                    "duration": job["duration"] or 0,
                                    "queued_duration": job["queued_duration"] or 0,
                                }

                                jobs_for_all_runners[job_id] = job_attr

                            continue

                        job_finished_at = datetime.strptime(
                            job["finished_at"], "%Y-%m-%dT%H:%M:%S.%fZ"
                        )

                        if job_finished_at > end_time:
                            continue
                        elif job_finished_at <= start_time:
                            stop = True
                            continue

                        job_attr = {
                            "group_id": self.mapping_list.get(job["project"]["id"]),
                            "runner_description": runner["description"],
                            "job_id": job["id"],
                            "job_name": job["name"],
                            "ref": job["ref"],
                            "status": job["status"],
                            "source": job['pipeline']['source'],
                            "pipeline_id": job["pipeline"]["id"],
                            "path_with_namespace": job["project"]["path_with_namespace"],
                            "duration": job["duration"] or 0,
                            "queued_duration": job["queued_duration"] or 0,
                        }

                        jobs_for_all_runners[job_id] = job_attr

                    if traverse_count == unfinished_job_length:
                        break

                    page += 1

                for job_id in jobs_to_remove:
                    self.unfinished_jobs[runner_id].remove(job_id)

                self.unfinished_jobs[runner_id].extend(current_unfinished_jobs)
                self.unfinished_jobs[runner_id].sort(reverse=True)

            logger.info(jobs_for_all_runners)
            return jobs_for_all_runners

        except Exception as e:
            logger.error(f"Error occurred while getting runners jobs: {e}")
