output "ecs_cluster_id" {
  value = aws_ecs_cluster.this.id
}

output "ecs_service_name" {
  value = aws_ecs_service.this.name
}

output "task_definition_arn" {
  value = aws_ecs_task_definition.this.arn
}

output "autoscaling_min_capacity" {
  value = var.autoscaling_min_capacity
}

output "autoscaling_max_capacity" {
  value = var.autoscaling_max_capacity
}

output "cpu_alarm_name" {
  value = aws_cloudwatch_metric_alarm.cpu_high.alarm_name
}

output "memory_alarm_name" {
  value = aws_cloudwatch_metric_alarm.memory_high.alarm_name
}
