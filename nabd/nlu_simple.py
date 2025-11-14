"""
Simple pattern-based Natural Language Understanding.
No external dependencies - just regex and Python standard library.
This is a lightweight replacement for Padatious/Snips NLU.
"""

import re
import traceback
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional, Dict, Any, List
import yaml
from datetime import datetime, timedelta

try:
    import dateparser
    HAS_DATEPARSER = True
except ImportError:
    HAS_DATEPARSER = False
    dateparser = None

from nabweb import settings


class SimpleNLU:
    """
    Simple pattern-based NLU using regex.
    API-compatible replacement for Snips/Padatious NLU.
    """

    ENGINES = {
        "en_US": "en",
        "en_GB": "en",
        "fr_FR": "fr",
    }
    DEFAULT_LOCALE = "fr_FR"

    @staticmethod
    def get_locale(locale):
        if locale in SimpleNLU.ENGINES:
            return locale
        else:
            return SimpleNLU.DEFAULT_LOCALE

    def __init__(self, locale):
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.locale = SimpleNLU.get_locale(locale)
        self.language = SimpleNLU.ENGINES[self.locale]
        self.intents = []
        self.entities = {}
        self._load_model(self.locale)

    def _load_model(self, locale):
        """Load intent patterns from YAML files."""
        try:
            locale = SimpleNLU.get_locale(locale)
            language = SimpleNLU.ENGINES[locale]
            
            basepath = Path(settings.BASE_DIR)
            
            # Load all intent files from services
            intent_files = self._discover_intent_files(basepath, language)
            
            # Parse YAML files
            for intent_file in intent_files:
                with open(intent_file, 'r', encoding='utf-8') as f:
                    content = yaml.safe_load_all(f)
                    for doc in content:
                        if doc is None:
                            continue
                        if doc.get('type') == 'entity':
                            # Store entity values
                            entity_name = doc['name']
                            entity_values = doc.get('values', [])
                            self.entities[entity_name] = entity_values
                        elif doc.get('type') == 'intent':
                            intent_name = doc['name']
                            utterances = doc.get('utterances', [])
                            # Convert each utterance to a regex pattern
                            for utterance in utterances:
                                pattern, slot_names = self._utterance_to_pattern(utterance)
                                self.intents.append({
                                    'name': intent_name,
                                    'pattern': pattern,
                                    'slots': slot_names,
                                    'original': utterance
                                })
            
        except Exception:
            print(traceback.format_exc())

    def _discover_intent_files(self, basepath: Path, language: str) -> List[Path]:
        """Find all intent YAML files for the given language."""
        intent_files = []
        
        # Search in all service directories
        for service_dir in basepath.glob("nab*/"):
            nlu_dir = service_dir / "nlu"
            if nlu_dir.exists():
                pattern = f"intent_*.{language}.yaml"
                for intent_file in nlu_dir.glob(pattern):
                    intent_files.append(intent_file)
        
        return sorted(intent_files)

    def _utterance_to_pattern(self, utterance: str) -> tuple:
        """
        Convert Snips/Padatious utterance format to regex pattern.
        
        Snips format: "what is the weather [date:snips/datetime](today)"
        Regex format: r"what is the weather (?P<date>.+)"
        
        Returns: (compiled_pattern, list_of_slot_names)
        """
        slot_names = []
        
        # Find all slots in format [slot_name:entity_type](example_value)
        # or simple {slot_name} format
        pattern_str = utterance
        
        # Handle Snips format: [slot:type](example)
        snips_pattern = r'\[([^:]+):([^\]]+)\]\(([^)]+)\)'
        def replace_snips(match):
            slot_name = match.group(1)
            slot_type = match.group(2)
            # example = match.group(3)  # Not used, just for documentation
            slot_names.append((slot_name, slot_type))
            
            # Create appropriate regex based on slot type
            if 'datetime' in slot_type.lower():
                # Match date/time expressions loosely
                return r'(?P<' + slot_name + r'>\w+(?:\s+\w+)*)'
            else:
                # Match any word sequence
                return r'(?P<' + slot_name + r'>\w+(?:\s+\w+)*)'
        
        pattern_str = re.sub(snips_pattern, replace_snips, pattern_str)
        
        # Handle simple format: {slot_name}
        simple_pattern = r'\{([^}]+)\}'
        def replace_simple(match):
            slot_name = match.group(1)
            slot_names.append((slot_name, 'text'))
            return r'(?P<' + slot_name + r'>\w+(?:\s+\w+)*)'
        
        pattern_str = re.sub(simple_pattern, replace_simple, pattern_str)
        
        # Make pattern case-insensitive and flexible with spacing
        pattern_str = r'\s*'.join(re.escape(word) if word else '' 
                                  for word in pattern_str.split())
        pattern_str = r'^\s*' + pattern_str + r'\s*$'
        
        try:
            compiled = re.compile(pattern_str, re.IGNORECASE | re.UNICODE)
        except re.error:
            # Fallback to simple exact match if regex fails
            compiled = re.compile(re.escape(utterance), re.IGNORECASE)
        
        return compiled, slot_names

    def _parse_datetime(self, text: str, locale: str) -> Optional[Dict[str, Any]]:
        """Parse datetime from text and return in Snips-compatible format."""
        if HAS_DATEPARSER:
            # Use dateparser if available
            settings_dict = {
                'PREFER_DATES_FROM': 'future',
                'RETURN_AS_TIMEZONE_AWARE': True
            }
            dt = dateparser.parse(text, settings=settings_dict, languages=[locale[:2]])
            if dt:
                return {
                    'kind': 'InstantTime',
                    'value': dt.strftime('%Y-%m-%d %H:%M:%S %z')
                }
        
        # Fallback to simple pattern matching
        text_lower = text.lower()
        now = datetime.now()
        
        # French patterns
        if locale.startswith('fr'):
            if text_lower in ['aujourd\'hui', 'aujourdhui']:
                return {'kind': 'InstantTime', 'value': now.strftime('%Y-%m-%d %H:%M:%S +00:00')}
            elif text_lower == 'demain':
                tomorrow = now + timedelta(days=1)
                return {'kind': 'InstantTime', 'value': tomorrow.strftime('%Y-%m-%d %H:%M:%S +00:00')}
        # English patterns
        elif locale.startswith('en'):
            if text_lower == 'today':
                return {'kind': 'InstantTime', 'value': now.strftime('%Y-%m-%d %H:%M:%S +00:00')}
            elif text_lower == 'tomorrow':
                tomorrow = now + timedelta(days=1)
                return {'kind': 'InstantTime', 'value': tomorrow.strftime('%Y-%m-%d %H:%M:%S +00:00')}
        
        return None

    def interpret_sync(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Synchronously interpret natural language text.
        Returns dict with 'intent' and optional slot values, or None.
        """
        if not text or not text.strip():
            return None
        
        text = text.strip()
        best_match = None
        best_score = 0.0
        
        # Try to match against all intent patterns
        for intent_data in self.intents:
            match = intent_data['pattern'].match(text)
            if match:
                # Calculate a simple score based on match quality
                # Exact length match = higher score
                matched_len = len(match.group(0).strip())
                input_len = len(text)
                score = matched_len / max(input_len, 1)
                
                if score > best_score:
                    best_score = score
                    slots = {}
                    
                    # Extract slot values
                    for slot_name, slot_type in intent_data['slots']:
                        value = match.group(slot_name)
                        if value:
                            # Parse datetime slots specially
                            if 'datetime' in slot_type.lower():
                                parsed = self._parse_datetime(value, self.language)
                                if parsed:
                                    slots[slot_name] = parsed
                                else:
                                    slots[slot_name] = value
                            else:
                                slots[slot_name] = value
                    
                    best_match = {
                        'intent': intent_data['name'],
                        **slots
                    }
        
        return best_match

    async def interpret_async(self, text: str) -> Optional[Dict[str, Any]]:
        """Asynchronously interpret natural language text."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, self.interpret_sync, text)

    def interpret(self, text: str, locale: Optional[str] = None):
        """
        Main interpret method - compatible with Snips NLU API.
        Returns future that resolves to interpretation result.
        """
        return self.executor.submit(self.interpret_sync, text)


# Make SimpleNLU available as NLU for drop-in replacement
NLU = SimpleNLU
