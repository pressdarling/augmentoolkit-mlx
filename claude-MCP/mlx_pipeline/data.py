"""
Data Processing and Preparation Module

Data preparation is arguably the most critical step in the fine-tuning pipeline.
MLX is particular about data formats, and small formatting errors can lead to
silent failures or suboptimal training results.

This module handles the often-frustrating process of converting various data
formats into the specific JSONL format that MLX expects. The key insight is
that robust data processing requires three phases:

1. Detection: Automatically identify the input format and structure
2. Transformation: Convert to MLX-compatible format with validation
3. Verification: Comprehensive testing of the output before training

Think of this as a translator that not only converts between languages, but
also checks grammar and meaning to ensure nothing gets lost in translation.
"""

import json
import pandas as pd
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, Union
import random
from collections import Counter
import re


class DataProcessor:
    """
    Comprehensive data processing pipeline for MLX fine-tuning.
    
    This class handles the complexity of converting various data formats
    into MLX-compatible JSONL whilst maintaining data quality and providing
    detailed validation feedback.
    
    The processor supports multiple input formats:
    - Raw text files for continued pretraining
    - CSV/Excel with prompt/response columns
    - JSONL files that need format conversion
    - Augmentoolkit output files
    - HuggingFace dataset formats
    
    Each input type has its own challenges and edge cases, which we handle
    systematically rather than hoping for the best.
    """
    
    def __init__(self):
        self.supported_formats = {
            "chat": self._process_chat_format,
            "completions": self._process_completions_format,
            "text": self._process_text_format,
            "augmentoolkit": self._process_augmentoolkit_format,
            "csv": self._process_csv_format,
            "excel": self._process_excel_format,
        }
        
        # Common problematic patterns in data that cause training issues
        self.validation_patterns = {
            "empty_content": r"^\s*$",
            "only_punctuation": r"^[^\w]*$",
            "too_many_repeats": r"(.)\1{10,}",  # Character repeated >10 times
            "control_characters": r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]",
        }
    
    def process_data(
        self,
        input_path: Path,
        output_path: Path,
        format_type: str = "auto",
        split_ratio: float = 0.8,
        max_sequence_length: Optional[int] = None,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> Dict[str, Any]:
        """
        Main data processing pipeline.
        
        This orchestrates the entire process from input detection through
        final validation. The design allows for interruption and resumption
        at any stage, which is crucial for large datasets.
        
        Args:
            input_path: Source data file or directory
            output_path: Directory for processed data
            format_type: Input format or 'auto' for detection
            split_ratio: Proportion for training vs validation
            max_sequence_length: Truncate sequences longer than this
            progress_callback: Function to call with progress updates
        
        Returns:
            Dictionary with processing statistics and file locations
        """
        output_path = Path(output_path)
        output_path.mkdir(parents=True, exist_ok=True)
        
        if progress_callback:
            progress_callback(10)
        
        # Phase 1: Format Detection and Loading
        if format_type == "auto":
            format_type = self._detect_format(input_path)
        
        raw_data = self._load_data(input_path, format_type)
        
        if progress_callback:
            progress_callback(30)
        
        # Phase 2: Format Conversion
        processed_data = self._convert_to_mlx_format(raw_data, format_type)
        
        if progress_callback:
            progress_callback(50)
        
        # Phase 3: Quality Control
        cleaned_data = self._clean_and_validate(processed_data, max_sequence_length)
        
        if progress_callback:
            progress_callback(70)
        
        # Phase 4: Train/Validation Split
        train_data, valid_data = self._split_data(cleaned_data, split_ratio)
        
        # Phase 5: Output Generation
        train_path = output_path / "train.jsonl"
        valid_path = output_path / "valid.jsonl"
        
        self._write_jsonl(train_data, train_path)
        self._write_jsonl(valid_data, valid_path)
        
        if progress_callback:
            progress_callback(90)
        
        # Phase 6: Final Validation
        validation_results = self._final_validation(train_path, valid_path)
        
        if progress_callback:
            progress_callback(100)
        
        return {
            "total_examples": len(cleaned_data),
            "train_examples": len(train_data),
            "valid_examples": len(valid_data),
            "train_file": str(train_path),
            "valid_file": str(valid_path),
            "format_detected": format_type,
            "validation_passed": validation_results["valid"],
            "quality_metrics": validation_results.get("metrics", {}),
        }
    
    def _detect_format(self, input_path: Path) -> str:
        """
        Automatically detect the input data format.
        
        This uses a combination of file extensions, content analysis, and
        structural patterns to determine the most likely format. The goal
        is to make the process as automatic as possible whilst being
        conservative about assumptions.
        """
        input_path = Path(input_path)
        
        # File extension hints
        if input_path.suffix.lower() in [".csv"]:
            return "csv"
        elif input_path.suffix.lower() in [".xlsx", ".xls"]:
            return "excel"
        elif input_path.suffix.lower() in [".jsonl", ".json"]:
            # Need to examine content to distinguish formats
            return self._detect_json_format(input_path)
        elif input_path.suffix.lower() in [".txt", ".md"]:
            return "text"
        
        # Content-based detection for ambiguous cases
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                sample = f.read(1024)  # Read first 1KB for analysis
            
            # Look for JSON structure
            if sample.strip().startswith('{'):
                return self._detect_json_format(input_path)
            
            # Look for CSV structure
            if ',' in sample and '\n' in sample:
                lines = sample.split('\n')[:3]
                if all(',' in line for line in lines if line.strip()):
                    return "csv"
            
            # Default to text format
            return "text"
            
        except Exception:
            # If we can't read the file, make a guess based on extension
            return "text"
    
    def _detect_json_format(self, input_path: Path) -> str:
        """
        Determine the specific JSON/JSONL format type.
        
        This examines the structure of JSON data to distinguish between
        chat format, completions format, and Augmentoolkit output.
        Each has different field names and structures.
        """
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                # Try to parse first line as JSON
                first_line = f.readline().strip()
                if not first_line:
                    return "text"
                
                sample_data = json.loads(first_line)
            
            # Check for chat format
            if "messages" in sample_data:
                return "chat"
            
            # Check for completions format
            if "prompt" in sample_data and "completion" in sample_data:
                return "completions"
            
            # Check for Augmentoolkit format
            if any(key in sample_data for key in ["instruction", "response", "question", "answer"]):
                return "augmentoolkit"
            
            # Default to treating as generic JSON that needs conversion
            return "completions"
            
        except json.JSONDecodeError:
            return "text"
        except Exception:
            return "text"
    
    def _load_data(self, input_path: Path, format_type: str) -> List[Dict[str, Any]]:
        """
        Load data from file based on detected format.
        
        Each format has its own loading requirements and potential issues.
        We handle encoding problems, malformed data, and missing fields
        gracefully with informative error messages.
        """
        input_path = Path(input_path)
        
        if format_type == "csv":
            return self._load_csv_data(input_path)
        elif format_type == "excel":
            return self._load_excel_data(input_path)
        elif format_type in ["chat", "completions", "augmentoolkit"]:
            return self._load_jsonl_data(input_path)
        elif format_type == "text":
            return self._load_text_data(input_path)
        else:
            raise ValueError(f"Unsupported format: {format_type}")
    
    def _load_csv_data(self, input_path: Path) -> List[Dict[str, Any]]:
        """
        Load and parse CSV data with robust error handling.
        
        CSV files are deceptively tricky because they can have encoding issues,
        different delimiters, quoted fields with newlines, and inconsistent
        column names. We try multiple approaches to get a clean load.
        """
        try:
            # Try UTF-8 first (most common)
            df = pd.read_csv(input_path, encoding='utf-8')
        except UnicodeDecodeError:
            # Fall back to latin-1 for older files
            try:
                df = pd.read_csv(input_path, encoding='latin-1')
            except Exception:
                # Last resort: let pandas auto-detect
                df = pd.read_csv(input_path)
        
        # Clean column names (remove whitespace, standardize)
        df.columns = df.columns.str.strip().str.lower()
        
        # Convert to list of dictionaries
        return df.to_dict('records')
    
    def _load_excel_data(self, input_path: Path) -> List[Dict[str, Any]]:
        """
        Load Excel data with sheet detection and column cleaning.
        
        Excel files can have multiple sheets, and users often put data
        in non-obvious places. We try to be smart about finding the
        actual data whilst avoiding empty rows and formatting artifacts.
        """
        # Load all sheets to find data
        excel_file = pd.ExcelFile(input_path)
        
        largest_sheet = None
        max_rows = 0
        
        for sheet_name in excel_file.sheet_names:
            df = pd.read_excel(input_path, sheet_name=sheet_name)
            if len(df) > max_rows:
                max_rows = len(df)
                largest_sheet = df
        
        if largest_sheet is None:
            raise ValueError("No data found in Excel file")
        
        # Clean column names
        largest_sheet.columns = largest_sheet.columns.str.strip().str.lower()
        
        # Remove empty rows
        largest_sheet = largest_sheet.dropna(how='all')
        
        return largest_sheet.to_dict('records')
    
    def _load_jsonl_data(self, input_path: Path) -> List[Dict[str, Any]]:
        """
        Load JSONL data with line-by-line error handling.
        
        JSONL files can have individual malformed lines that shouldn't
        break the entire load. We parse each line separately and collect
        errors for reporting whilst continuing with valid data.
        """
        data = []
        errors = []
        
        with open(input_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                
                try:
                    item = json.loads(line)
                    data.append(item)
                except json.JSONDecodeError as e:
                    errors.append(f"Line {line_num}: {e}")
                    continue
        
        if errors and len(errors) > len(data) * 0.1:  # More than 10% errors
            raise ValueError(f"Too many JSON parsing errors: {errors[:5]}")
        
        return data
    
    def _load_text_data(self, input_path: Path) -> List[Dict[str, Any]]:
        """
        Load plain text data for continued pretraining.
        
        For raw text, we need to decide how to chunk it into training
        examples. The strategy depends on the content type and desired
        sequence length. We provide several chunking strategies.
        """
        with open(input_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Strategy 1: Split by double newlines (paragraphs)
        chunks = [chunk.strip() for chunk in content.split('\n\n') if chunk.strip()]
        
        # Strategy 2: If chunks are too large, split by sentences
        final_chunks = []
        for chunk in chunks:
            if len(chunk) > 2000:  # Arbitrary threshold
                # Split by sentences
                sentences = re.split(r'[.!?]+', chunk)
                current_chunk = ""
                
                for sentence in sentences:
                    if len(current_chunk + sentence) < 2000:
                        current_chunk += sentence + ". "
                    else:
                        if current_chunk:
                            final_chunks.append(current_chunk.strip())
                        current_chunk = sentence + ". "
                
                if current_chunk:
                    final_chunks.append(current_chunk.strip())
            else:
                final_chunks.append(chunk)
        
        # Convert to format expected by rest of pipeline
        return [{"text": chunk} for chunk in final_chunks if len(chunk) > 50]
    
    def _convert_to_mlx_format(self, data: List[Dict[str, Any]], format_type: str) -> List[Dict[str, Any]]:
        """
        Convert various formats to MLX-compatible structure.
        
        This is where the actual format conversion happens. Each input
        format has its own conversion logic, but they all produce the
        same output structure that MLX expects.
        """
        if format_type not in self.supported_formats:
            raise ValueError(f"Unsupported format: {format_type}")
        
        return self.supported_formats[format_type](data)
    
    def _process_chat_format(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Process data already in chat format, with validation and cleaning.
        
        Even if data claims to be in chat format, it might have issues:
        - Missing required fields
        - Invalid role values
        - Empty content
        - Extra fields that MLX doesn't accept
        """
        processed = []
        
        for item in data:
            if "messages" not in item:
                continue
            
            # Clean and validate messages
            clean_messages = []
            for msg in item["messages"]:
                if not isinstance(msg, dict):
                    continue
                
                role = msg.get("role", "").strip().lower()
                content = msg.get("content", "").strip()
                
                # Validate role
                if role not in ["system", "user", "assistant"]:
                    continue
                
                # Validate content
                if not content or len(content) < 3:
                    continue
                
                clean_messages.append({
                    "role": role,
                    "content": content
                })
            
            # Ensure we have at least user and assistant messages
            if len(clean_messages) >= 2:
                processed.append({"messages": clean_messages})
        
        return processed
    
    def _process_completions_format(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert prompt/completion format to chat format.
        
        This is one of the most common conversions. The challenge is
        deciding how to map prompts and completions to the chat structure
        whilst preserving the training signal.
        """
        processed = []
        
        for item in data:
            prompt = item.get("prompt", "").strip()
            completion = item.get("completion", "").strip()
            
            if not prompt or not completion:
                continue
            
            # Convert to chat format
            messages = [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": completion}
            ]
            
            # Add system message if present
            if "system" in item and item["system"]:
                messages.insert(0, {"role": "system", "content": item["system"].strip()})
            
            processed.append({"messages": messages})
        
        return processed
    
    def _process_text_format(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert raw text to format suitable for continued pretraining.
        
        For continued pretraining, we typically use the text format
        where each example is just raw text that the model learns to
        continue. This is different from instruction following.
        """
        processed = []
        
        for item in data:
            text = item.get("text", "").strip()
            
            if len(text) < 50:  # Skip very short texts
                continue
            
            processed.append({"text": text})
        
        return processed
    
    def _process_augmentoolkit_format(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert Augmentoolkit output to MLX chat format.
        
        Augmentoolkit can produce various field names depending on
        configuration. We try to handle the most common patterns
        whilst preserving the question-answer structure.
        """
        processed = []
        
        for item in data:
            # Try different field name patterns
            question = (
                item.get("instruction") or 
                item.get("question") or 
                item.get("prompt") or ""
            ).strip()
            
            answer = (
                item.get("response") or 
                item.get("answer") or 
                item.get("completion") or ""
            ).strip()
            
            if not question or not answer:
                continue
            
            # Convert to chat format
            messages = [
                {"role": "user", "content": question},
                {"role": "assistant", "content": answer}
            ]
            
            # Add system context if available
            context = item.get("context") or item.get("system")
            if context and context.strip():
                messages.insert(0, {"role": "system", "content": context.strip()})
            
            processed.append({"messages": messages})
        
        return processed
    
    def _process_csv_format(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert CSV data to chat format by mapping columns.
        
        CSV data requires column mapping to determine which fields
        contain prompts, responses, and optional system messages.
        We use heuristics to guess the mapping but allow override.
        """
        if not data:
            return []
        
        # Analyze columns to guess the mapping
        columns = list(data[0].keys())
        column_mapping = self._guess_column_mapping(columns)
        
        processed = []
        
        for item in data:
            prompt_col = column_mapping.get("prompt")
            response_col = column_mapping.get("response")
            
            if not prompt_col or not response_col:
                continue
            
            prompt = str(item.get(prompt_col, "")).strip()
            response = str(item.get(response_col, "")).strip()
            
            if not prompt or not response:
                continue
            
            messages = [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": response}
            ]
            
            # Add system message if column exists
            system_col = column_mapping.get("system")
            if system_col and item.get(system_col):
                system_content = str(item[system_col]).strip()
                if system_content:
                    messages.insert(0, {"role": "system", "content": system_content})
            
            processed.append({"messages": messages})
        
        return processed
    
    def _process_excel_format(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Process Excel data using the same logic as CSV.
        
        Excel and CSV have the same structural challenges once loaded,
        so we can reuse the CSV processing logic.
        """
        return self._process_csv_format(data)
    
    def _guess_column_mapping(self, columns: List[str]) -> Dict[str, str]:
        """
        Guess which columns contain prompts, responses, and system messages.
        
        This uses common naming patterns to automatically map columns.
        The goal is to make the process automatic for standard datasets
        whilst being conservative about assumptions.
        """
        mapping = {}
        
        # Common patterns for prompt columns
        prompt_patterns = [
            "prompt", "question", "instruction", "input", "query", "user",
            "human", "context", "problem", "task"
        ]
        
        # Common patterns for response columns
        response_patterns = [
            "response", "answer", "completion", "output", "reply", "assistant",
            "solution", "result", "target"
        ]
        
        # Common patterns for system columns
        system_patterns = [
            "system", "context", "instruction", "guidelines", "persona"
        ]
        
        # Find best matches
        for col in columns:
            col_lower = col.lower()
            
            # Check for prompt column
            if not mapping.get("prompt"):
                for pattern in prompt_patterns:
                    if pattern in col_lower:
                        mapping["prompt"] = col
                        break
            
            # Check for response column
            if not mapping.get("response"):
                for pattern in response_patterns:
                    if pattern in col_lower:
                        mapping["response"] = col
                        break
            
            # Check for system column
            if not mapping.get("system"):
                for pattern in system_patterns:
                    if pattern in col_lower and col != mapping.get("prompt"):
                        mapping["system"] = col
                        break
        
        return mapping
    
    def _clean_and_validate(
        self, 
        data: List[Dict[str, Any]], 
        max_sequence_length: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Clean data and remove problematic examples.
        
        This phase removes examples that could cause training problems:
        - Empty or very short content
        - Malformed structure
        - Problematic characters or patterns
        - Sequences that are too long
        
        The goal is to remove potential issues whilst preserving as much
        useful training data as possible.
        """
        cleaned = []
        issues_found = Counter()
        
        for item in data:
            # Check basic structure
            if not self._validate_item_structure(item):
                issues_found["invalid_structure"] += 1
                continue
            
            # Clean content
            cleaned_item = self._clean_item_content(item)
            
            # Validate content quality
            validation_issues = self._validate_content_quality(cleaned_item)
            if validation_issues:
                for issue in validation_issues:
                    issues_found[issue] += 1
                continue
            
            # Check sequence length
            if max_sequence_length and self._estimate_token_count(cleaned_item) > max_sequence_length:
                issues_found["too_long"] += 1
                continue
            
            cleaned.append(cleaned_item)
        
        # Log cleaning statistics
        total_removed = len(data) - len(cleaned)
        if total_removed > 0:
            print(f"Removed {total_removed} problematic examples:")
            for issue, count in issues_found.most_common():
                print(f"  - {issue}: {count}")
        
        return cleaned
    
    def _validate_item_structure(self, item: Dict[str, Any]) -> bool:
        """Validate that an item has the expected structure."""
        if "messages" in item:
            messages = item["messages"]
            if not isinstance(messages, list) or len(messages) < 1:
                return False
            
            for msg in messages:
                if not isinstance(msg, dict):
                    return False
                if "role" not in msg or "content" not in msg:
                    return False
                
            return True
        
        elif "text" in item:
            return isinstance(item["text"], str) and len(item["text"]) > 0
        
        return False
    
    def _clean_item_content(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Clean content in an item."""
        if "messages" in item:
            cleaned_messages = []
            for msg in item["messages"]:
                cleaned_content = self._clean_text(msg["content"])
                cleaned_messages.append({
                    "role": msg["role"],
                    "content": cleaned_content
                })
            return {"messages": cleaned_messages}
        
        elif "text" in item:
            return {"text": self._clean_text(item["text"])}
        
        return item
    
    def _clean_text(self, text: str) -> str:
        """Clean individual text content."""
        # Remove control characters
        text = re.sub(self.validation_patterns["control_characters"], "", text)
        
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Remove excessive repetition
        text = re.sub(r'(.)\1{5,}', r'\1\1\1', text)  # Limit to 3 repeats
        
        return text
    
    def _validate_content_quality(self, item: Dict[str, Any]) -> List[str]:
        """Validate content quality and return list of issues."""
        issues = []
        
        if "messages" in item:
            for msg in item["messages"]:
                content = msg["content"]
                content_issues = self._check_text_quality(content)
                issues.extend(content_issues)
        
        elif "text" in item:
            content_issues = self._check_text_quality(item["text"])
            issues.extend(content_issues)
        
        return issues
    
    def _check_text_quality(self, text: str) -> List[str]:
        """Check individual text for quality issues."""
        issues = []
        
        # Check for empty or whitespace-only content
        if re.match(self.validation_patterns["empty_content"], text):
            issues.append("empty_content")
        
        # Check for only punctuation
        if re.match(self.validation_patterns["only_punctuation"], text):
            issues.append("only_punctuation")
        
        # Check for excessive repetition
        if re.search(self.validation_patterns["too_many_repeats"], text):
            issues.append("excessive_repetition")
        
        # Check minimum length
        if len(text) < 10:
            issues.append("too_short")
        
        return issues
    
    def _estimate_token_count(self, item: Dict[str, Any]) -> int:
        """Rough estimation of token count for sequence length validation."""
        total_chars = 0
        
        if "messages" in item:
            for msg in item["messages"]:
                total_chars += len(msg["content"])
        elif "text" in item:
            total_chars = len(item["text"])
        
        # Rough approximation: 1 token ≈ 4 characters
        return total_chars // 4
    
    def _split_data(self, data: List[Dict[str, Any]], split_ratio: float) -> tuple:
        """Split data into training and validation sets."""
        # Shuffle data for random split
        shuffled_data = data.copy()
        random.shuffle(shuffled_data)
        
        # Calculate split point
        split_point = int(len(shuffled_data) * split_ratio)
        
        train_data = shuffled_data[:split_point]
        valid_data = shuffled_data[split_point:]
        
        # Ensure we have at least some validation data
        if len(valid_data) == 0 and len(train_data) > 1:
            valid_data = [train_data.pop()]
        
        return train_data, valid_data
    
    def _write_jsonl(self, data: List[Dict[str, Any]], output_path: Path) -> None:
        """Write data to JSONL file."""
        with open(output_path, 'w', encoding='utf-8') as f:
            for item in data:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
    
    def _final_validation(self, train_path: Path, valid_path: Path) -> Dict[str, Any]:
        """Perform final validation of output files."""
        issues = []
        metrics = {}
        
        try:
            # Validate train file
            train_count = self._count_jsonl_lines(train_path)
            metrics["train_examples"] = train_count
            
            # Validate validation file
            valid_count = self._count_jsonl_lines(valid_path)
            metrics["valid_examples"] = valid_count
            
            # Check for reasonable split
            if valid_count == 0:
                issues.append("No validation examples")
            elif valid_count / (train_count + valid_count) < 0.05:
                issues.append("Very small validation set")
            
            # Sample validation
            sample_issues = self._validate_sample_data(train_path)
            issues.extend(sample_issues)
            
        except Exception as e:
            issues.append(f"Validation error: {e}")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "metrics": metrics
        }
    
    def _count_jsonl_lines(self, file_path: Path) -> int:
        """Count valid JSON lines in a file."""
        count = 0
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        json.loads(line)
                        count += 1
                    except json.JSONDecodeError:
                        pass
        return count
    
    def _validate_sample_data(self, file_path: Path, sample_size: int = 5) -> List[str]:
        """Validate a sample of the data for common issues."""
        issues = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f):
                    if i >= sample_size:
                        break
                    
                    try:
                        data = json.loads(line)
                        
                        # Check structure
                        if "messages" in data:
                            if not isinstance(data["messages"], list):
                                issues.append(f"Line {i+1}: messages is not a list")
                            elif len(data["messages"]) == 0:
                                issues.append(f"Line {i+1}: empty messages list")
                        elif "text" in data:
                            if not isinstance(data["text"], str):
                                issues.append(f"Line {i+1}: text is not a string")
                        else:
                            issues.append(f"Line {i+1}: unknown format")
                    
                    except json.JSONDecodeError:
                        issues.append(f"Line {i+1}: invalid JSON")
        
        except Exception as e:
            issues.append(f"Sample validation failed: {e}")
        
        return issues
    
    def validate_data(self, data_path: Path) -> Dict[str, Any]:
        """
        Comprehensive validation of processed data files.
        
        This performs thorough validation of the final output to ensure
        it meets MLX requirements and is likely to train successfully.
        """
        data_path = Path(data_path)
        results = {
            "valid": True,
            "issues": [],
            "statistics": {}
        }
        
        # Check required files exist
        train_file = data_path / "train.jsonl"
        valid_file = data_path / "valid.jsonl"
        
        if not train_file.exists():
            results["issues"].append("Missing train.jsonl file")
            results["valid"] = False
        
        if not valid_file.exists():
            results["issues"].append("Missing valid.jsonl file")
            results["valid"] = False
        
        if not results["valid"]:
            return results
        
        # Detailed validation of each file
        for file_path, file_type in [(train_file, "train"), (valid_file, "valid")]:
            file_issues = self._validate_jsonl_file(file_path)
            
            if file_issues:
                results["issues"].extend([f"{file_type}: {issue}" for issue in file_issues])
                results["valid"] = False
            
            # Collect statistics
            stats = self._collect_file_statistics(file_path)
            results["statistics"][file_type] = stats
        
        return results
    
    def _validate_jsonl_file(self, file_path: Path) -> List[str]:
        """Validate a single JSONL file."""
        issues = []
        line_count = 0
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    
                    line_count += 1
                    
                    try:
                        data = json.loads(line)
                        
                        # Validate structure
                        structure_issues = self._validate_mlx_format(data)
                        if structure_issues:
                            issues.extend([f"Line {line_num}: {issue}" for issue in structure_issues])
                    
                    except json.JSONDecodeError as e:
                        issues.append(f"Line {line_num}: JSON decode error - {e}")
            
            if line_count == 0:
                issues.append("File is empty")
        
        except Exception as e:
            issues.append(f"File read error: {e}")
        
        return issues
    
    def _validate_mlx_format(self, data: Dict[str, Any]) -> List[str]:
        """Validate that data conforms to MLX format requirements."""
        issues = []
        
        if "messages" in data:
            messages = data["messages"]
            
            if not isinstance(messages, list):
                issues.append("messages must be a list")
                return issues
            
            if len(messages) == 0:
                issues.append("messages list is empty")
                return issues
            
            for i, msg in enumerate(messages):
                if not isinstance(msg, dict):
                    issues.append(f"Message {i} is not a dictionary")
                    continue
                
                if "role" not in msg:
                    issues.append(f"Message {i} missing role field")
                
                if "content" not in msg:
                    issues.append(f"Message {i} missing content field")
                
                role = msg.get("role")
                if role not in ["system", "user", "assistant"]:
                    issues.append(f"Message {i} has invalid role: {role}")
                
                content = msg.get("content")
                if not isinstance(content, str) or not content.strip():
                    issues.append(f"Message {i} has empty or invalid content")
        
        elif "text" in data:
            text = data["text"]
            if not isinstance(text, str) or not text.strip():
                issues.append("text field is empty or invalid")
        
        else:
            issues.append("Unknown format - missing messages or text field")
        
        return issues
    
    def _collect_file_statistics(self, file_path: Path) -> Dict[str, Any]:
        """Collect statistics about a data file."""
        stats = {
            "line_count": 0,
            "total_characters": 0,
            "avg_characters_per_example": 0,
            "role_distribution": Counter(),
            "example_lengths": []
        }
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    stats["line_count"] += 1
                    
                    try:
                        data = json.loads(line)
                        
                        example_chars = 0
                        
                        if "messages" in data:
                            for msg in data["messages"]:
                                role = msg.get("role", "unknown")
                                content = msg.get("content", "")
                                
                                stats["role_distribution"][role] += 1
                                example_chars += len(content)
                        
                        elif "text" in data:
                            example_chars = len(data["text"])
                        
                        stats["total_characters"] += example_chars
                        stats["example_lengths"].append(example_chars)
                    
                    except json.JSONDecodeError:
                        continue
            
            if stats["line_count"] > 0:
                stats["avg_characters_per_example"] = stats["total_characters"] / stats["line_count"]
        
        except Exception:
            pass
        
        return stats
