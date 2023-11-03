import logging
from prometheus_client import Counter, Gauge, generate_latest
import requests


class PrometheusExporter:
    def __init__(self):
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        self.metrics = {}  # Dictionary to store the metrics

    def add_gauge_metric(self, metric_name, metric_description, labelnames):
        # Create Prometheus Gauge metric
        metric = Gauge(metric_name, metric_description, labelnames)
        self.metrics[metric_name] = metric

    def add_counter_metric(self, metric_name, metric_description, labelnames=[]):
        # Create Prometheus Gauge metric
        metric = Counter(metric_name, metric_description, labelnames)
        self.metrics[metric_name] = metric

    def increment_metric(self, metric_name, labels, value=1):
        if metric_name in self.metrics:
            self.metrics[metric_name].labels(**labels).inc(value)

    def set_metric(self, metric_name, labels, value):
        if metric_name in self.metrics:
            self.metrics[metric_name].labels(**labels).set(value)

    def clear_metrics(self):
        for metric in self.metrics.values():
            metric._metrics.clear()

    def generate_customed_metrics(self):
        # Generate latest metrics for all registered metrics
        for metric in self.metrics.values():
            self.logger.info(generate_latest(metric).decode("utf-8"))
            