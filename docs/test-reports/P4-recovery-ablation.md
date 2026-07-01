# Recovery Ablation 实验报告

## 总场景数: 10

## 指标

- resume_success_rate: 40.00%
- stale_reanchor_rate: 0.00%
- workspace_drift_detection_rate: 0.00%
- resume_false_accept_rate: 0.00%
- enabled_success_rate: 40.00%
- disabled_success_rate: 10.00%

## 详细结果

### resume_enabled（开启 checkpoint）

| 场景 | 状态 | 成功 | 耗时 |
|------|------|------|------|
| checkpoint_resume | full-valid | PASS | 2ms |
| partial_stale | full-valid | FAIL | 5ms |
| workspace_mismatch | full-valid | FAIL | 3ms |
| schema_mismatch | full-valid | FAIL | 3ms |
| partial_success | full-valid | PASS | 5ms |
| file_created | full-valid | PASS | 3ms |
| file_renamed | error | FAIL | 2ms |
| content_swapped | full-valid | FAIL | 3ms |
| multiple_changes | full-valid | FAIL | 8ms |
| no_checkpoint | none | PASS | 0ms |

### resume_disabled（关闭 checkpoint）

| 场景 | 状态 | 成功 | 耗时 |
|------|------|------|------|
| checkpoint_resume | none | FAIL | 2ms |
| partial_stale | none | FAIL | 2ms |
| workspace_mismatch | none | FAIL | 2ms |
| schema_mismatch | none | FAIL | 1ms |
| partial_success | none | FAIL | 2ms |
| file_created | none | FAIL | 1ms |
| file_renamed | error | FAIL | 0ms |
| content_swapped | none | FAIL | 2ms |
| multiple_changes | none | FAIL | 5ms |
| no_checkpoint | none | PASS | 0ms |
