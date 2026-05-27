# tethering

A Python library for managing multi-stage CLM runs on PBS clusters.

CLM cases are typically submitted as independent PBS jobs. Tethering chains them together into a pipeline. Each stage automatically submits the next when it completes, using PBS `afterok` dependencies to ensure correct ordering.

> **Status**: Early development. The API may change.
