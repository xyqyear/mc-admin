"""Example tasks for demonstrating the task system."""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from .executor import TaskExecutionContext
from .registry import register_system_task

logger = logging.getLogger(__name__)


@register_system_task(
    name="dns_sync_check",
    description="检查本地服务器配置是否和DNS同步",
    metadata={"category": "system", "priority": "high"}
)
async def dns_sync_check(context: TaskExecutionContext) -> Dict[str, Any]:
    """持续运行的后台任务：检查本地服务器配置是否和DNS同步。
    
    这是一个示例后台任务，实际实现会检查Minecraft服务器配置与DNS记录的同步状态。
    """
    await context.update_metadata({"check_type": "dns_sync", "started_at": datetime.now().isoformat()})
    
    logger.info("Starting DNS sync check")
    
    try:
        # 模拟DNS查询和本地配置比较
        await asyncio.sleep(2)  # 模拟网络请求
        
        # 模拟检查结果
        local_servers = ["server1.example.com", "server2.example.com"]
        dns_records = ["server1.example.com", "server2.example.com", "server3.example.com"]
        
        out_of_sync = []
        missing_local = []
        
        for record in dns_records:
            if record not in local_servers:
                missing_local.append(record)
        
        for server in local_servers:
            if server not in dns_records:
                out_of_sync.append(server)
        
        result = {
            "status": "completed",
            "timestamp": datetime.now().isoformat(),
            "local_servers": local_servers,
            "dns_records": dns_records,
            "out_of_sync_servers": out_of_sync,
            "missing_local_servers": missing_local,
            "sync_status": "synced" if not out_of_sync and not missing_local else "out_of_sync"
        }
        
        await context.set_result(result)
        
        if result["sync_status"] == "out_of_sync":
            logger.warning(f"DNS sync issues detected: {len(out_of_sync)} out of sync, {len(missing_local)} missing locally")
        else:
            logger.info("DNS configuration is synchronized")
        
        return result
        
    except Exception as e:
        logger.error(f"DNS sync check failed: {e}")
        error_result = {
            "status": "failed",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }
        
        await context.set_result(error_result)
        
        return error_result


@register_system_task(
    name="server_restart",
    description="重启指定的Minecraft服务器",
    metadata={"category": "server_management", "priority": "medium"}
)
async def server_restart(context: TaskExecutionContext, server_id: str, reason: str = "Manual restart") -> Dict[str, Any]:
    """一次性任务：用户提交的服务器重启任务。
    
    Args:
        context: 任务执行上下文
        server_id: 要重启的服务器ID
        reason: 重启原因
    """
    await context.update_metadata({
        "server_id": server_id,
        "reason": reason,
        "task_type": "server_restart"
    })
    
    logger.info(f"Starting server restart for {server_id}, reason: {reason}")
    
    try:
        # 模拟服务器重启过程
        steps = [
            ("stopping_server", "正在停止服务器", 3),
            ("waiting_shutdown", "等待服务器完全停止", 2),
            ("starting_server", "正在启动服务器", 4),
            ("health_check", "检查服务器健康状态", 2)
        ]
        
        result = {
            "server_id": server_id,
            "reason": reason,
            "status": "in_progress",
            "steps": [],
            "start_time": datetime.now().isoformat()
        }
        
        for step_id, description, duration in steps:
            logger.info(f"Server {server_id}: {description}")
            
            step_result = {
                "step": step_id,
                "description": description,
                "status": "running",
                "start_time": datetime.now().isoformat()
            }
            
            await context.update_metadata({"current_step": step_id, "step_description": description})
            
            # 模拟步骤执行时间
            await asyncio.sleep(duration)
            
            step_result["status"] = "completed"
            step_result["end_time"] = datetime.now().isoformat()
            step_result["duration_seconds"] = duration
            
            result["steps"].append(step_result)
        
        # 完成重启
        result.update({
            "status": "completed",
            "end_time": datetime.now().isoformat(),
            "message": f"服务器 {server_id} 重启成功"
        })
        
        await context.set_result(result)
        
        logger.info(f"Server restart completed successfully for {server_id}")
        return result
        
    except Exception as e:
        logger.error(f"Server restart failed for {server_id}: {e}")
        error_result = {
            "server_id": server_id,
            "status": "failed",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }
        
        await context.set_result(error_result)
        
        return error_result


@register_system_task(
    name="daily_server_restart",
    description="每日自动重启服务器",
    metadata={"category": "maintenance", "priority": "low"}
)
async def daily_server_restart(context: TaskExecutionContext, server_ids: Optional[list[str]] = None) -> Dict[str, Any]:
    """定时任务：每天的服务器自动重启。
    
    Args:
        context: 任务执行上下文
        server_ids: 要重启的服务器ID列表，如果为None则重启所有服务器
    """
    await context.update_metadata({
        "task_type": "daily_restart",
        "scheduled": True,
        "target_servers": server_ids or "all"
    })
    
    logger.info("Starting daily server restart routine")
    
    try:
        # 如果没有指定服务器，使用默认列表
        if server_ids is None:
            server_ids = ["server1", "server2", "server3"]
        
        result = {
            "task_type": "daily_restart",
            "start_time": datetime.now().isoformat(),
            "target_servers": server_ids,
            "server_results": [],
            "status": "in_progress"
        }
        
        successful_restarts = 0
        failed_restarts = 0
        
        for server_id in server_ids:
            logger.info(f"Processing daily restart for server: {server_id}")
            
            try:
                # 为每个服务器创建一个新的上下文，但这里简化处理
                # 在实际应用中，你可能想要创建子任务或者不同的处理方式
                # 这里我们直接模拟重启操作而不是调用另一个任务
                logger.info(f"Restarting server {server_id} for daily maintenance...")
                await asyncio.sleep(5)  # 模拟重启时间
                
                server_result = {
                    "server_id": server_id,
                    "status": "completed",
                    "message": f"Server {server_id} restarted successfully",
                    "timestamp": datetime.now().isoformat()
                }
                
                if server_result.get("status") == "completed":
                    successful_restarts += 1
                else:
                    failed_restarts += 1
                
                result["server_results"].append({
                    "server_id": server_id,
                    "status": server_result.get("status", "unknown"),
                    "result": server_result
                })
                
            except Exception as e:
                failed_restarts += 1
                logger.error(f"Failed to restart server {server_id}: {e}")
                result["server_results"].append({
                    "server_id": server_id,
                    "status": "failed",
                    "error": str(e)
                })
            
            # 服务器重启之间等待一段时间
            await asyncio.sleep(30)
        
        # 完成任务
        result.update({
            "status": "completed",
            "end_time": datetime.now().isoformat(),
            "summary": {
                "total_servers": len(server_ids),
                "successful": successful_restarts,
                "failed": failed_restarts,
                "success_rate": f"{(successful_restarts / len(server_ids) * 100):.1f}%"
            }
        })
        
        await context.set_result(result)
        
        logger.info(
            f"Daily restart completed: {successful_restarts}/{len(server_ids)} servers restarted successfully"
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Daily restart routine failed: {e}")
        error_result = {
            "task_type": "daily_restart",
            "status": "failed",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }
        
        await context.set_result(error_result)
        
        return error_result


@register_system_task(
    name="health_check",
    description="系统健康检查任务",
    metadata={"category": "monitoring", "priority": "high"}
)
async def health_check(context: TaskExecutionContext) -> Dict[str, Any]:
    """系统健康检查任务示例。"""
    await context.update_metadata({"check_type": "system_health"})
    
    logger.info("Starting system health check")
    
    try:
        # 模拟各种健康检查
        checks = [
            ("database", "数据库连接"),
            ("disk_space", "磁盘空间"),
            ("memory", "内存使用"),
            ("cpu", "CPU负载"),
            ("services", "服务状态")
        ]
        
        result = {
            "status": "running",
            "start_time": datetime.now().isoformat(),
            "checks": {}
        }
        
        all_passed = True
        
        for check_id, description in checks:
            logger.debug(f"Performing health check: {description}")
            
            # 模拟检查
            await asyncio.sleep(0.5)
            
            # 模拟随机成功/失败（大部分成功）
            import random
            passed = random.random() > 0.1  # 90% success rate
            
            check_result = {
                "description": description,
                "status": "passed" if passed else "failed",
                "timestamp": datetime.now().isoformat()
            }
            
            if not passed:
                all_passed = False
                check_result["error"] = f"模拟的 {description} 检查失败"
            
            result["checks"][check_id] = check_result
        
        result.update({
            "status": "completed",
            "end_time": datetime.now().isoformat(),
            "overall_status": "healthy" if all_passed else "unhealthy",
            "passed_checks": sum(1 for c in result["checks"].values() if c["status"] == "passed"),
            "total_checks": len(checks)
        })
        
        await context.set_result(result)
        
        logger.info(f"Health check completed: {result['overall_status']}")
        return result
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        error_result = {
            "status": "failed",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }
        
        await context.set_result(error_result)
        
        return error_result