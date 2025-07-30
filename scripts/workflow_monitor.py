#!/usr/bin/env python3
"""
Workflow Monitor for GGUF Sync
Monitors and reports on GitHub Actions workflow performance and status.
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import argparse


class WorkflowMonitor:
    """Monitor and analyze GGUF sync workflow performance."""
    
    def __init__(self, reports_dir: str = "reports"):
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(exist_ok=True)
        
    def load_report(self, report_file: str) -> Optional[Dict[str, Any]]:
        """Load a JSON report file."""
        try:
            report_path = self.reports_dir / report_file
            if report_path.exists():
                with open(report_path, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load {report_file}: {e}")
        return None
    
    def get_latest_workflow_status(self) -> Dict[str, Any]:
        """Get the status of the latest workflow run."""
        status = {
            "workflow_id": os.getenv("WORKFLOW_RUN_ID", "unknown"),
            "status": "unknown",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "reports_found": []
        }
        
        # Check for various report files
        report_files = [
            "workflow_summary.json",
            "performance_report.json",
            "sync_failure_report.json",
            "push_failure.json",
            "no_changes_report.json"
        ]
        
        for report_file in report_files:
            report = self.load_report(report_file)
            if report:
                status["reports_found"].append(report_file)
                
                # Update status based on report type
                if report_file == "sync_failure_report.json":
                    status["status"] = "sync_failed"
                    status.update(report)
                elif report_file == "push_failure.json":
                    status["status"] = "push_failed"
                    status.update(report)
                elif report_file == "workflow_summary.json":
                    status.update(report)
                elif report_file == "performance_report.json":
                    status["performance"] = report
                elif report_file == "no_changes_report.json":
                    status["status"] = "no_changes"
                    status.update(report)
        
        return status
    
    def analyze_performance_trends(self) -> Dict[str, Any]:
        """Analyze performance trends from historical data."""
        trends = {
            "analysis_timestamp": datetime.utcnow().isoformat() + "Z",
            "total_reports": 0,
            "success_rate": 0.0,
            "average_duration": 0.0,
            "average_models_count": 0.0,
            "performance_issues": []
        }
        
        # Look for historical performance reports
        performance_files = list(self.reports_dir.glob("performance_report*.json"))
        if not performance_files:
            trends["performance_issues"].append("No historical performance data found")
            return trends
        
        successful_runs = []
        failed_runs = []
        
        for perf_file in performance_files:
            try:
                with open(perf_file, 'r') as f:
                    data = json.load(f)
                    
                if data.get("files_status") == "success":
                    successful_runs.append(data)
                else:
                    failed_runs.append(data)
                    
            except Exception as e:
                print(f"Warning: Could not analyze {perf_file}: {e}")
        
        total_runs = len(successful_runs) + len(failed_runs)
        trends["total_reports"] = total_runs
        
        if total_runs > 0:
            trends["success_rate"] = len(successful_runs) / total_runs * 100
            
            if successful_runs:
                durations = [run.get("duration_minutes", 0) for run in successful_runs]
                models_counts = [run.get("models_count", 0) for run in successful_runs]
                
                trends["average_duration"] = sum(durations) / len(durations)
                trends["average_models_count"] = sum(models_counts) / len(models_counts)
                
                # Identify performance issues
                if trends["average_duration"] > 240:  # 4 hours
                    trends["performance_issues"].append(
                        f"Average duration ({trends['average_duration']:.1f} min) exceeds 4 hours"
                    )
                
                if trends["success_rate"] < 95:
                    trends["performance_issues"].append(
                        f"Success rate ({trends['success_rate']:.1f}%) below 95% threshold"
                    )
        
        return trends
    
    def generate_status_report(self) -> Dict[str, Any]:
        """Generate a comprehensive status report."""
        current_status = self.get_latest_workflow_status()
        performance_trends = self.analyze_performance_trends()
        
        report = {
            "report_timestamp": datetime.utcnow().isoformat() + "Z",
            "current_workflow": current_status,
            "performance_trends": performance_trends,
            "system_health": self._assess_system_health(current_status, performance_trends),
            "recommendations": self._generate_recommendations(current_status, performance_trends)
        }
        
        return report
    
    def _assess_system_health(self, current_status: Dict, trends: Dict) -> Dict[str, Any]:
        """Assess overall system health."""
        health = {
            "overall_status": "healthy",
            "issues": [],
            "warnings": []
        }
        
        # Check current workflow status
        if current_status.get("status") in ["sync_failed", "push_failed"]:
            health["overall_status"] = "critical"
            health["issues"].append(f"Current workflow failed: {current_status.get('status')}")
        
        # Check performance trends
        if trends.get("success_rate", 100) < 90:
            health["overall_status"] = "degraded"
            health["issues"].append(f"Low success rate: {trends.get('success_rate', 0):.1f}%")
        elif trends.get("success_rate", 100) < 95:
            health["warnings"].append(f"Success rate below optimal: {trends.get('success_rate', 0):.1f}%")
        
        # Check duration trends
        if trends.get("average_duration", 0) > 300:  # 5 hours
            health["overall_status"] = "degraded"
            health["issues"].append(f"Excessive duration: {trends.get('average_duration', 0):.1f} minutes")
        elif trends.get("average_duration", 0) > 240:  # 4 hours
            health["warnings"].append(f"Duration approaching limit: {trends.get('average_duration', 0):.1f} minutes")
        
        return health
    
    def _generate_recommendations(self, current_status: Dict, trends: Dict) -> List[str]:
        """Generate actionable recommendations."""
        recommendations = []
        
        # Performance recommendations
        if trends.get("average_duration", 0) > 180:  # 3 hours
            recommendations.append("Consider increasing MAX_CONCURRENCY to reduce processing time")
            recommendations.append("Monitor rate limiting and adjust delays if needed")
        
        # Reliability recommendations
        if trends.get("success_rate", 100) < 95:
            recommendations.append("Review error logs to identify common failure patterns")
            recommendations.append("Consider implementing additional retry mechanisms")
        
        # Current status recommendations
        if current_status.get("status") == "sync_failed":
            recommendations.append("Check Hugging Face API status and token validity")
            recommendations.append("Review network connectivity and rate limiting")
        elif current_status.get("status") == "push_failed":
            recommendations.append("Check GitHub token permissions and repository access")
            recommendations.append("Verify git configuration and branch protection rules")
        
        # General recommendations
        if not recommendations:
            recommendations.append("System is operating normally - continue monitoring")
        
        return recommendations
    
    def print_status_summary(self):
        """Print a human-readable status summary."""
        report = self.generate_status_report()
        
        print("=" * 60)
        print("🤖 GGUF Sync Workflow Monitor")
        print("=" * 60)
        print()
        
        # Current status
        current = report["current_workflow"]
        print(f"📊 Current Workflow Status: {current.get('status', 'unknown').upper()}")
        print(f"🆔 Workflow ID: {current.get('workflow_id', 'unknown')}")
        print(f"⏰ Last Update: {current.get('timestamp', 'unknown')}")
        print()
        
        # Performance metrics
        if "performance" in current:
            perf = current["performance"]
            print("📈 Current Performance:")
            print(f"   Duration: {perf.get('duration_minutes', 0)} minutes")
            print(f"   Models: {perf.get('models_count', 0)}")
            print(f"   Attempts: {perf.get('total_attempts', 1)}")
            print(f"   Concurrency: {perf.get('max_concurrency', 'unknown')}")
            print()
        
        # Trends
        trends = report["performance_trends"]
        print("📊 Performance Trends:")
        print(f"   Success Rate: {trends.get('success_rate', 0):.1f}%")
        print(f"   Average Duration: {trends.get('average_duration', 0):.1f} minutes")
        print(f"   Average Models: {trends.get('average_models_count', 0):.0f}")
        print(f"   Total Reports: {trends.get('total_reports', 0)}")
        print()
        
        # System health
        health = report["system_health"]
        status_emoji = {"healthy": "✅", "degraded": "⚠️", "critical": "🚨"}
        print(f"🏥 System Health: {status_emoji.get(health['overall_status'], '❓')} {health['overall_status'].upper()}")
        
        if health["issues"]:
            print("   Issues:")
            for issue in health["issues"]:
                print(f"   🚨 {issue}")
        
        if health["warnings"]:
            print("   Warnings:")
            for warning in health["warnings"]:
                print(f"   ⚠️ {warning}")
        print()
        
        # Recommendations
        recommendations = report["recommendations"]
        if recommendations:
            print("💡 Recommendations:")
            for i, rec in enumerate(recommendations, 1):
                print(f"   {i}. {rec}")
        print()
        
        print("=" * 60)
    
    def save_status_report(self, filename: str = None):
        """Save the status report to a file."""
        if filename is None:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"workflow_status_report_{timestamp}.json"
        
        report = self.generate_status_report()
        
        output_path = self.reports_dir / filename
        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"📄 Status report saved to: {output_path}")
        return output_path


def main():
    """Main entry point for the workflow monitor."""
    parser = argparse.ArgumentParser(description="Monitor GGUF sync workflow performance")
    parser.add_argument("--reports-dir", default="reports", help="Directory containing workflow reports")
    parser.add_argument("--save-report", action="store_true", help="Save detailed report to file")
    parser.add_argument("--quiet", action="store_true", help="Suppress console output")
    
    args = parser.parse_args()
    
    monitor = WorkflowMonitor(args.reports_dir)
    
    if not args.quiet:
        monitor.print_status_summary()
    
    if args.save_report:
        monitor.save_status_report()
    
    # Exit with appropriate code based on system health
    report = monitor.generate_status_report()
    health_status = report["system_health"]["overall_status"]
    
    if health_status == "critical":
        sys.exit(2)
    elif health_status == "degraded":
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()