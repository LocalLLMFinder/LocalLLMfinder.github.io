#!/usr/bin/env python3
"""
Comprehensive Data Validation and Quality Assurance System

This module provides comprehensive validation, quality scoring, and automatic
data fixing capabilities for GGUF model data processing.
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Any, Set, Tuple, Union
from urllib.parse import urlparse
import aiohttp
from pathlib import Path

logger = logging.getLogger(__name__)

class ValidationSeverity(Enum):
    """Severity levels for validation issues."""
    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

class ValidationCategory(Enum):
    """Categories of validation issues."""
    SCHEMA = "schema"
    DATA_INTEGRITY = "data_integrity"
    FILE_ACCESS = "file_access"
    COMPLETENESS = "completeness"
    QUALITY = "quality"
    CONSISTENCY = "consistency"

@dataclass
class ValidationIssue:
    """Represents a validation issue found during data validation."""
    category: ValidationCategory
    severity: ValidationSeverity
    field: str
    message: str
    model_id: Optional[str] = None
    file_name: Optional[str] = None
    suggested_fix: Optional[str] = None
    auto_fixable: bool = False
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

@dataclass
class ValidationResult:
    """Result of validation for a single model or file."""
    is_valid: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    quality_score: float = 0.0
    completeness_score: float = 0.0
    auto_fixes_applied: int = 0
    validation_time: float = 0.0

@dataclass
class QualityMetrics:
    """Quality metrics for model data."""
    total_models: int = 0
    valid_models: int = 0
    invalid_models: int = 0
    models_with_warnings: int = 0
    total_files: int = 0
    accessible_files: int = 0
    inaccessible_files: int = 0
    auto_fixes_applied: int = 0
    average_quality_score: float = 0.0
    average_completeness_score: float = 0.0
    validation_duration: float = 0.0
    
    @property
    def validation_success_rate(self) -> float:
        """Calculate validation success rate."""
        return (self.valid_models / self.total_models * 100) if self.total_models > 0 else 0.0
    
    @property
    def file_accessibility_rate(self) -> float:
        """Calculate file accessibility rate."""
        return (self.accessible_files / self.total_files * 100) if self.total_files > 0 else 0.0

class SchemaValidator:
    """Validates model data against predefined schemas."""
    
    def __init__(self):
        self.model_schema = self._define_model_schema()
        self.file_schema = self._define_file_schema()
        self.metadata_schema = self._define_metadata_schema()
    
    def _define_model_schema(self) -> Dict[str, Any]:
        """Define the schema for model data."""
        return {
            "required_fields": [
                "id", "name", "files", "downloads", "architecture", "family",
                "description", "tags", "likes", "created_at", "last_modified"
            ],
            "optional_fields": [
                "license", "library_name", "pipeline_tag", "base_model",
                "model_index", "widget", "datasets", "metrics", "co2_eq_emissions"
            ],
            "field_types": {
                "id": str,
                "name": str,
                "files": list,
                "downloads": (int, float),
                "architecture": str,
                "family": str,
                "description": str,
                "tags": list,
                "likes": (int, float),
                "created_at": str,
                "last_modified": str,
                "license": str,
                "library_name": str,
                "pipeline_tag": str
            },
            "field_constraints": {
                "id": {"pattern": r"^[^/]+/[^/]+$", "min_length": 3},
                "name": {"min_length": 1, "max_length": 200},
                "downloads": {"min_value": 0},
                "likes": {"min_value": 0},
                "files": {"min_length": 1},
                "tags": {"max_length": 50}
            }
        }
    
    def _define_file_schema(self) -> Dict[str, Any]:
        """Define the schema for file data."""
        return {
            "required_fields": [
                "filename", "size", "sizeBytes", "quantization", "downloadUrl"
            ],
            "optional_fields": [
                "sha256", "lfs", "rfilename", "oid"
            ],
            "field_types": {
                "filename": str,
                "size": str,
                "sizeBytes": (int, float),
                "quantization": str,
                "downloadUrl": str,
                "sha256": str,
                "lfs": dict,
                "rfilename": str,
                "oid": str
            },
            "field_constraints": {
                "filename": {"pattern": r".*\.gguf$", "min_length": 5},
                "sizeBytes": {"min_value": 0},
                "downloadUrl": {"pattern": r"^https://.*"},
                "quantization": {"allowed_values": [
                    "Q4_K_M", "Q4_K_S", "Q5_K_M", "Q5_K_S", "Q3_K_M", "Q3_K_S", "Q3_K_L",
                    "Q6_K", "Q2_K", "Q8_0", "Q4_0", "Q4_1", "Q5_0", "Q5_1", "F16", "F32",
                    "IQ1_S", "IQ1_M", "IQ2_XXS", "IQ2_XS", "IQ2_S", "IQ2_M",
                    "IQ3_XXS", "IQ3_S", "IQ3_M", "IQ4_XS", "IQ4_NL", "BF16", "Unknown"
                ]}
            }
        }
    
    def _define_metadata_schema(self) -> Dict[str, Any]:
        """Define the schema for metadata."""
        return {
            "required_fields": [
                "generated_at", "total_models", "generation_time", "next_update"
            ],
            "optional_fields": [
                "discovery_methods", "validation_summary", "quality_metrics"
            ],
            "field_types": {
                "generated_at": str,
                "total_models": int,
                "generation_time": (int, float),
                "next_update": str
            }
        }
    
    def validate_model(self, model_data: Dict[str, Any]) -> ValidationResult:
        """Validate a single model against the schema."""
        start_time = time.time()
        issues = []
        
        # Validate required fields
        issues.extend(self._validate_required_fields(
            model_data, self.model_schema["required_fields"], "model"
        ))
        
        # Validate field types
        issues.extend(self._validate_field_types(
            model_data, self.model_schema["field_types"], "model"
        ))
        
        # Validate field constraints
        issues.extend(self._validate_field_constraints(
            model_data, self.model_schema["field_constraints"], "model"
        ))
        
        # Additional specific validations
        if "name" in model_data and model_data["name"] == "":
            issues.append(ValidationIssue(
                category=ValidationCategory.DATA_INTEGRITY,
                severity=ValidationSeverity.ERROR,
                field="name",
                message="Empty name for model",
                suggested_fix="Generate name from model ID",
                auto_fixable=True
            ))
        
        # Validate files array
        if "files" in model_data and isinstance(model_data["files"], list):
            for i, file_data in enumerate(model_data["files"]):
                file_issues = self.validate_file(file_data, f"files[{i}]")
                issues.extend(file_issues.issues)
        
        # Calculate scores
        quality_score = self._calculate_quality_score(model_data, issues)
        completeness_score = self._calculate_completeness_score(model_data)
        
        validation_time = time.time() - start_time
        
        return ValidationResult(
            is_valid=not any(issue.severity in [ValidationSeverity.CRITICAL, ValidationSeverity.ERROR] for issue in issues),
            issues=issues,
            quality_score=quality_score,
            completeness_score=completeness_score,
            validation_time=validation_time
        )
    
    def validate_file(self, file_data: Dict[str, Any], context: str = "file") -> ValidationResult:
        """Validate a single file against the schema."""
        start_time = time.time()
        issues = []
        
        # Validate required fields
        issues.extend(self._validate_required_fields(
            file_data, self.file_schema["required_fields"], context
        ))
        
        # Validate field types
        issues.extend(self._validate_field_types(
            file_data, self.file_schema["field_types"], context
        ))
        
        # Validate field constraints
        issues.extend(self._validate_field_constraints(
            file_data, self.file_schema["field_constraints"], context
        ))
        
        # Calculate scores
        quality_score = self._calculate_file_quality_score(file_data, issues)
        completeness_score = self._calculate_file_completeness_score(file_data)
        
        validation_time = time.time() - start_time
        
        return ValidationResult(
            is_valid=not any(issue.severity in [ValidationSeverity.CRITICAL, ValidationSeverity.ERROR] for issue in issues),
            issues=issues,
            quality_score=quality_score,
            completeness_score=completeness_score,
            validation_time=validation_time
        )
    
    def _validate_required_fields(self, data: Dict[str, Any], required_fields: List[str], context: str) -> List[ValidationIssue]:
        """Validate that all required fields are present."""
        issues = []
        
        for field in required_fields:
            if field not in data:
                issues.append(ValidationIssue(
                    category=ValidationCategory.SCHEMA,
                    severity=ValidationSeverity.CRITICAL,
                    field=field,
                    message=f"Missing required field '{field}' in {context}",
                    suggested_fix=f"Add '{field}' field to {context}",
                    auto_fixable=False
                ))
            elif data[field] is None:
                issues.append(ValidationIssue(
                    category=ValidationCategory.SCHEMA,
                    severity=ValidationSeverity.ERROR,
                    field=field,
                    message=f"Required field '{field}' is null in {context}",
                    suggested_fix=f"Provide a valid value for '{field}'",
                    auto_fixable=True
                ))
        
        return issues
    
    def _validate_field_types(self, data: Dict[str, Any], field_types: Dict[str, Any], context: str) -> List[ValidationIssue]:
        """Validate field types."""
        issues = []
        
        for field, expected_type in field_types.items():
            if field in data and data[field] is not None:
                if not isinstance(data[field], expected_type):
                    issues.append(ValidationIssue(
                        category=ValidationCategory.SCHEMA,
                        severity=ValidationSeverity.ERROR,
                        field=field,
                        message=f"Field '{field}' has incorrect type in {context}. Expected {expected_type}, got {type(data[field])}",
                        suggested_fix=f"Convert '{field}' to {expected_type}",
                        auto_fixable=True
                    ))
        
        return issues
    
    def _validate_field_constraints(self, data: Dict[str, Any], constraints: Dict[str, Dict], context: str) -> List[ValidationIssue]:
        """Validate field constraints."""
        issues = []
        
        for field, constraint_dict in constraints.items():
            if field not in data or data[field] is None:
                continue
            
            value = data[field]
            
            # Pattern validation
            if "pattern" in constraint_dict and isinstance(value, str):
                if not re.match(constraint_dict["pattern"], value):
                    issues.append(ValidationIssue(
                        category=ValidationCategory.DATA_INTEGRITY,
                        severity=ValidationSeverity.ERROR,
                        field=field,
                        message=f"Field '{field}' does not match required pattern in {context}",
                        suggested_fix=f"Ensure '{field}' matches pattern: {constraint_dict['pattern']}",
                        auto_fixable=False
                    ))
            
            # Length validation
            if "min_length" in constraint_dict:
                if hasattr(value, '__len__') and len(value) < constraint_dict["min_length"]:
                    issues.append(ValidationIssue(
                        category=ValidationCategory.DATA_INTEGRITY,
                        severity=ValidationSeverity.ERROR,
                        field=field,
                        message=f"Field '{field}' is too short in {context}. Minimum length: {constraint_dict['min_length']}",
                        suggested_fix=f"Ensure '{field}' has at least {constraint_dict['min_length']} characters/items",
                        auto_fixable=False
                    ))
            
            if "max_length" in constraint_dict:
                if hasattr(value, '__len__') and len(value) > constraint_dict["max_length"]:
                    issues.append(ValidationIssue(
                        category=ValidationCategory.DATA_INTEGRITY,
                        severity=ValidationSeverity.WARNING,
                        field=field,
                        message=f"Field '{field}' is too long in {context}. Maximum length: {constraint_dict['max_length']}",
                        suggested_fix=f"Truncate '{field}' to {constraint_dict['max_length']} characters/items",
                        auto_fixable=True
                    ))
            
            # Value validation
            if "min_value" in constraint_dict and isinstance(value, (int, float)):
                if value < constraint_dict["min_value"]:
                    issues.append(ValidationIssue(
                        category=ValidationCategory.DATA_INTEGRITY,
                        severity=ValidationSeverity.ERROR,
                        field=field,
                        message=f"Field '{field}' value is too low in {context}. Minimum: {constraint_dict['min_value']}",
                        suggested_fix=f"Set '{field}' to at least {constraint_dict['min_value']}",
                        auto_fixable=True
                    ))
            
            # Allowed values validation
            if "allowed_values" in constraint_dict:
                if value not in constraint_dict["allowed_values"]:
                    issues.append(ValidationIssue(
                        category=ValidationCategory.DATA_INTEGRITY,
                        severity=ValidationSeverity.WARNING,
                        field=field,
                        message=f"Field '{field}' has unexpected value '{value}' in {context}",
                        suggested_fix=f"Use one of the allowed values: {constraint_dict['allowed_values'][:5]}...",
                        auto_fixable=True
                    ))
        
        return issues
    
    def _calculate_quality_score(self, model_data: Dict[str, Any], issues: List[ValidationIssue]) -> float:
        """Calculate quality score for a model (0-100)."""
        base_score = 100.0
        
        # Deduct points for issues
        for issue in issues:
            if issue.severity == ValidationSeverity.CRITICAL:
                base_score -= 25
            elif issue.severity == ValidationSeverity.ERROR:
                base_score -= 10
            elif issue.severity == ValidationSeverity.WARNING:
                base_score -= 5
            elif issue.severity == ValidationSeverity.INFO:
                base_score -= 1
        
        # Bonus points for completeness
        optional_fields = self.model_schema["optional_fields"]
        present_optional = sum(1 for field in optional_fields if field in model_data and model_data[field])
        completeness_bonus = (present_optional / len(optional_fields)) * 10
        
        return max(0.0, min(100.0, base_score + completeness_bonus))
    
    def _calculate_completeness_score(self, model_data: Dict[str, Any]) -> float:
        """Calculate completeness score for a model (0-100)."""
        all_fields = self.model_schema["required_fields"] + self.model_schema["optional_fields"]
        present_fields = sum(1 for field in all_fields if field in model_data and model_data[field])
        
        return (present_fields / len(all_fields)) * 100
    
    def _calculate_file_quality_score(self, file_data: Dict[str, Any], issues: List[ValidationIssue]) -> float:
        """Calculate quality score for a file (0-100)."""
        base_score = 100.0
        
        # Deduct points for issues
        for issue in issues:
            if issue.severity == ValidationSeverity.CRITICAL:
                base_score -= 30
            elif issue.severity == ValidationSeverity.ERROR:
                base_score -= 15
            elif issue.severity == ValidationSeverity.WARNING:
                base_score -= 7
            elif issue.severity == ValidationSeverity.INFO:
                base_score -= 2
        
        return max(0.0, min(100.0, base_score))
    
    def _calculate_file_completeness_score(self, file_data: Dict[str, Any]) -> float:
        """Calculate completeness score for a file (0-100)."""
        all_fields = self.file_schema["required_fields"] + self.file_schema["optional_fields"]
        present_fields = sum(1 for field in all_fields if field in file_data and file_data[field])
        
        return (present_fields / len(all_fields)) * 100

class FileAccessibilityVerifier:
    """Verifies accessibility of GGUF files."""
    
    def __init__(self, session: aiohttp.ClientSession, timeout: int = 30, max_concurrent: int = 10):
        self.session = session
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.verification_cache: Dict[str, Tuple[bool, datetime]] = {}
        self.cache_duration = 3600  # 1 hour cache
    
    async def verify_file_accessibility(self, file_data: Dict[str, Any]) -> ValidationResult:
        """Verify that a GGUF file is accessible via its download URL."""
        start_time = time.time()
        issues = []
        
        download_url = file_data.get("downloadUrl")
        filename = file_data.get("filename", "unknown")
        
        if not download_url:
            issues.append(ValidationIssue(
                category=ValidationCategory.FILE_ACCESS,
                severity=ValidationSeverity.CRITICAL,
                field="downloadUrl",
                message=f"Missing download URL for file {filename}",
                file_name=filename,
                auto_fixable=False
            ))
            return ValidationResult(
                is_valid=False,
                issues=issues,
                validation_time=time.time() - start_time
            )
        
        # Check cache first
        if download_url in self.verification_cache:
            is_accessible, cached_time = self.verification_cache[download_url]
            if (datetime.now(timezone.utc) - cached_time).total_seconds() < self.cache_duration:
                if not is_accessible:
                    issues.append(ValidationIssue(
                        category=ValidationCategory.FILE_ACCESS,
                        severity=ValidationSeverity.ERROR,
                        field="downloadUrl",
                        message=f"File {filename} is not accessible (cached result)",
                        file_name=filename,
                        auto_fixable=False
                    ))
                
                return ValidationResult(
                    is_valid=is_accessible,
                    issues=issues,
                    validation_time=time.time() - start_time
                )
        
        # Perform actual verification
        async with self.semaphore:
            is_accessible = await self._check_url_accessibility(download_url)
        
        # Cache result
        self.verification_cache[download_url] = (is_accessible, datetime.now(timezone.utc))
        
        if not is_accessible:
            issues.append(ValidationIssue(
                category=ValidationCategory.FILE_ACCESS,
                severity=ValidationSeverity.ERROR,
                field="downloadUrl",
                message=f"File {filename} is not accessible at {download_url}",
                file_name=filename,
                suggested_fix="Verify the download URL is correct and the file exists",
                auto_fixable=False
            ))
        
        validation_time = time.time() - start_time
        
        return ValidationResult(
            is_valid=is_accessible,
            issues=issues,
            validation_time=validation_time
        )
    
    async def _check_url_accessibility(self, url: str) -> bool:
        """Check if a URL is accessible via HEAD request."""
        try:
            async with self.session.head(url, timeout=self.timeout, allow_redirects=True) as response:
                # Consider 2xx and 3xx status codes as accessible
                return 200 <= response.status < 400
        except asyncio.TimeoutError:
            logger.debug(f"Timeout checking accessibility of {url}")
            return False
        except Exception as e:
            logger.debug(f"Error checking accessibility of {url}: {e}")
            return False
    
    def clear_cache(self):
        """Clear the verification cache."""
        self.verification_cache.clear()
        logger.info("File accessibility verification cache cleared")

class DataFixer:
    """Automatically fixes common data validation errors."""
    
    def __init__(self):
        self.fix_count = 0
    
    def fix_model_data(self, model_data: Dict[str, Any], issues: List[ValidationIssue]) -> Tuple[Dict[str, Any], int]:
        """Apply automatic fixes to model data."""
        fixed_data = model_data.copy()
        fixes_applied = 0
        
        for issue in issues:
            if issue.auto_fixable:
                fix_applied = self._apply_fix(fixed_data, issue)
                if fix_applied:
                    fixes_applied += 1
        
        self.fix_count += fixes_applied
        return fixed_data, fixes_applied
    
    def _apply_fix(self, data: Dict[str, Any], issue: ValidationIssue) -> bool:
        """Apply a specific fix to the data."""
        try:
            field = issue.field
            
            # Fix null or empty required fields
            if "is null" in issue.message or "is too short" in issue.message or "Empty name" in issue.message:
                if field == "name" and "id" in data:
                    data[field] = self._extract_name_from_id(data["id"])
                    return True
                elif field == "description":
                    data[field] = f"GGUF model: {data.get('name', data.get('id', 'Unknown'))}"
                    return True
                elif field == "architecture":
                    data[field] = self._guess_architecture(data)
                    return True
                elif field == "family":
                    data[field] = data.get("id", "").split("/")[0] if "/" in data.get("id", "") else "Unknown"
                    return True
                elif field in ["downloads", "likes"] and isinstance(data.get(field), str):
                    try:
                        data[field] = int(data[field])
                        return True
                    except ValueError:
                        data[field] = 0
                        return True
            
            # Fix type issues
            if "incorrect type" in issue.message:
                if field in ["downloads", "likes"] and isinstance(data.get(field), str):
                    try:
                        data[field] = int(data[field])
                        return True
                    except ValueError:
                        data[field] = 0
                        return True
                elif field == "tags" and not isinstance(data.get(field), list):
                    data[field] = []
                    return True
            
            # Fix length issues
            if "too long" in issue.message and "max_length" in issue.suggested_fix:
                max_length = int(re.search(r'(\d+)', issue.suggested_fix).group(1))
                if isinstance(data.get(field), str):
                    data[field] = data[field][:max_length]
                    return True
                elif isinstance(data.get(field), list):
                    data[field] = data[field][:max_length]
                    return True
            
            # Fix value constraints
            if "too low" in issue.message and field in ["downloads", "likes"]:
                data[field] = 0
                return True
            
            # Fix quantization values
            if field == "quantization" and "unexpected value" in issue.message:
                data[field] = self._guess_quantization(data.get("filename", ""))
                return True
            
            return False
            
        except Exception as e:
            logger.debug(f"Failed to apply fix for {issue.field}: {e}")
            return False
    
    def _extract_name_from_id(self, model_id: str) -> str:
        """Extract a readable name from model ID."""
        if "/" in model_id:
            name = model_id.split("/", 1)[1]
        else:
            name = model_id
        
        # Clean up the name
        name = re.sub(r'[-_]', ' ', name)
        name = re.sub(r'\b(gguf|ggml)\b', '', name, flags=re.IGNORECASE)
        name = ' '.join(word.capitalize() for word in name.split())
        
        return name.strip() or "Unknown Model"
    
    def _guess_architecture(self, model_data: Dict[str, Any]) -> str:
        """Guess architecture from model ID and tags."""
        model_id = model_data.get("id", "").lower()
        tags = [tag.lower() for tag in model_data.get("tags", [])]
        
        # Common architecture patterns
        architectures = {
            "llama": ["llama", "llama-2", "llama-3"],
            "mistral": ["mistral", "mixtral"],
            "qwen": ["qwen", "qwen2"],
            "gemma": ["gemma"],
            "phi": ["phi", "phi-3"],
            "falcon": ["falcon"],
            "mpt": ["mpt"],
            "bloom": ["bloom"],
            "gpt": ["gpt", "chatgpt"],
            "claude": ["claude"],
            "vicuna": ["vicuna"],
            "alpaca": ["alpaca"]
        }
        
        for arch, patterns in architectures.items():
            if any(pattern in model_id for pattern in patterns) or any(pattern in tag for tag in tags for pattern in patterns):
                return arch.capitalize()
        
        return "Unknown"
    
    def _guess_quantization(self, filename: str) -> str:
        """Guess quantization from filename."""
        filename_lower = filename.lower()
        
        # Common quantization patterns
        quantizations = [
            "Q4_K_M", "Q4_K_S", "Q5_K_M", "Q5_K_S", "Q3_K_M", "Q3_K_S", "Q3_K_L",
            "Q6_K", "Q2_K", "Q8_0", "Q4_0", "Q4_1", "Q5_0", "Q5_1", "F16", "F32",
            "IQ1_S", "IQ1_M", "IQ2_XXS", "IQ2_XS", "IQ2_S", "IQ2_M",
            "IQ3_XXS", "IQ3_S", "IQ3_M", "IQ4_XS", "IQ4_NL", "BF16"
        ]
        
        for quant in quantizations:
            if quant.lower() in filename_lower:
                return quant
        
        return "Unknown"

class DataValidationEngine:
    """Main validation engine that orchestrates all validation components."""
    
    def __init__(self, session: aiohttp.ClientSession):
        self.schema_validator = SchemaValidator()
        self.file_verifier = FileAccessibilityVerifier(session)
        self.data_fixer = DataFixer()
        self.metrics = QualityMetrics()
    
    async def validate_models_batch(self, models: List[Dict[str, Any]], 
                                  verify_file_access: bool = True,
                                  apply_auto_fixes: bool = True) -> Tuple[List[Dict[str, Any]], QualityMetrics]:
        """Validate a batch of models with comprehensive validation."""
        start_time = time.time()
        logger.info(f"🔍 Starting comprehensive validation of {len(models)} models...")
        
        validated_models = []
        total_issues = []
        
        # Reset metrics
        self.metrics = QualityMetrics()
        self.metrics.total_models = len(models)
        
        for i, model_data in enumerate(models):
            model_id = model_data.get("id", f"model_{i}")
            
            try:
                # Schema validation
                validation_result = self.schema_validator.validate_model(model_data)
                
                # File accessibility verification
                if verify_file_access and "files" in model_data:
                    for file_data in model_data.get("files", []):
                        file_result = await self.file_verifier.verify_file_accessibility(file_data)
                        validation_result.issues.extend(file_result.issues)
                        self.metrics.total_files += 1
                        if file_result.is_valid:
                            self.metrics.accessible_files += 1
                        else:
                            self.metrics.inaccessible_files += 1
                
                # Apply automatic fixes if enabled
                fixed_model = model_data
                fixes_applied = 0
                
                if apply_auto_fixes:
                    fixed_model, fixes_applied = self.data_fixer.fix_model_data(
                        model_data, validation_result.issues
                    )
                    self.metrics.auto_fixes_applied += fixes_applied
                    validation_result.auto_fixes_applied = fixes_applied
                    
                    # Re-validate after fixes
                    if fixes_applied > 0:
                        validation_result = self.schema_validator.validate_model(fixed_model)
                
                # Update metrics
                if validation_result.is_valid:
                    self.metrics.valid_models += 1
                else:
                    self.metrics.invalid_models += 1
                
                if any(issue.severity == ValidationSeverity.WARNING for issue in validation_result.issues):
                    self.metrics.models_with_warnings += 1
                
                # Add validation metadata to model
                fixed_model["_validation"] = {
                    "is_valid": validation_result.is_valid,
                    "quality_score": validation_result.quality_score,
                    "completeness_score": validation_result.completeness_score,
                    "issues_count": len(validation_result.issues),
                    "auto_fixes_applied": fixes_applied,
                    "validated_at": datetime.now(timezone.utc).isoformat()
                }
                
                validated_models.append(fixed_model)
                total_issues.extend(validation_result.issues)
                
                # Log progress
                if (i + 1) % max(1, len(models) // 10) == 0:
                    progress = ((i + 1) / len(models)) * 100
                    logger.info(f"📊 Validation progress: {i + 1}/{len(models)} ({progress:.1f}%)")
            
            except Exception as e:
                logger.error(f"❌ Error validating model {model_id}: {e}")
                self.metrics.invalid_models += 1
                # Include the model even if validation failed
                model_data["_validation"] = {
                    "is_valid": False,
                    "quality_score": 0.0,
                    "completeness_score": 0.0,
                    "issues_count": 1,
                    "auto_fixes_applied": 0,
                    "error": str(e),
                    "validated_at": datetime.now(timezone.utc).isoformat()
                }
                validated_models.append(model_data)
        
        # Calculate final metrics
        self.metrics.validation_duration = time.time() - start_time
        
        if validated_models:
            quality_scores = [m.get("_validation", {}).get("quality_score", 0) for m in validated_models]
            completeness_scores = [m.get("_validation", {}).get("completeness_score", 0) for m in validated_models]
            
            self.metrics.average_quality_score = sum(quality_scores) / len(quality_scores)
            self.metrics.average_completeness_score = sum(completeness_scores) / len(completeness_scores)
        
        # Log validation summary
        self._log_validation_summary(total_issues)
        
        return validated_models, self.metrics
    
    def _log_validation_summary(self, issues: List[ValidationIssue]):
        """Log comprehensive validation summary."""
        logger.info("📋 Validation Summary:")
        logger.info(f"   • Total models: {self.metrics.total_models}")
        logger.info(f"   • Valid models: {self.metrics.valid_models} ({self.metrics.validation_success_rate:.1f}%)")
        logger.info(f"   • Invalid models: {self.metrics.invalid_models}")
        logger.info(f"   • Models with warnings: {self.metrics.models_with_warnings}")
        logger.info(f"   • Total files: {self.metrics.total_files}")
        logger.info(f"   • Accessible files: {self.metrics.accessible_files} ({self.metrics.file_accessibility_rate:.1f}%)")
        logger.info(f"   • Auto-fixes applied: {self.metrics.auto_fixes_applied}")
        logger.info(f"   • Average quality score: {self.metrics.average_quality_score:.1f}/100")
        logger.info(f"   • Average completeness score: {self.metrics.average_completeness_score:.1f}/100")
        logger.info(f"   • Validation duration: {self.metrics.validation_duration:.1f}s")
        
        # Log issue breakdown
        if issues:
            issue_breakdown = {}
            for issue in issues:
                key = f"{issue.category.value}_{issue.severity.value}"
                issue_breakdown[key] = issue_breakdown.get(key, 0) + 1
            
            logger.info("📊 Issue Breakdown:")
            for issue_type, count in sorted(issue_breakdown.items()):
                logger.info(f"   • {issue_type}: {count}")
    
    def generate_validation_report(self) -> Dict[str, Any]:
        """Generate comprehensive validation report."""
        return {
            "validation_summary": {
                "total_models": self.metrics.total_models,
                "valid_models": self.metrics.valid_models,
                "invalid_models": self.metrics.invalid_models,
                "models_with_warnings": self.metrics.models_with_warnings,
                "validation_success_rate": self.metrics.validation_success_rate,
                "average_quality_score": self.metrics.average_quality_score,
                "average_completeness_score": self.metrics.average_completeness_score,
                "validation_duration": self.metrics.validation_duration
            },
            "file_accessibility": {
                "total_files": self.metrics.total_files,
                "accessible_files": self.metrics.accessible_files,
                "inaccessible_files": self.metrics.inaccessible_files,
                "accessibility_rate": self.metrics.file_accessibility_rate
            },
            "auto_fixes": {
                "total_fixes_applied": self.metrics.auto_fixes_applied
            },
            "generated_at": datetime.now(timezone.utc).isoformat()
        }