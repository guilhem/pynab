"""
Natural Language Understanding using Padatious.
This replaces the Snips NLU implementation with a lighter, more maintainable solution.
"""

import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional, Dict, Any
import yaml

try:
    from padatious import IntentContainer  # type: ignore
    import dateparser  # type: ignore

    HAS_NLU_DEPENDENCIES = True
except ImportError:
    HAS_NLU_DEPENDENCIES = False
    IntentContainer = None  # type: ignore
    dateparser = None  # type: ignore

from nabweb import settings


class NLU:
    """
    Class handling natural language understanding using Padatious.
    API-compatible replacement for Snips NLU implementation.
    """

    ENGINES = {
        "en_US": "en",
        "en_GB": "en",
        "fr_FR": "fr",
    }
    DEFAULT_LOCALE = "fr_FR"

    @staticmethod
    def get_locale(locale):
        if locale in NLU.ENGINES:
            return locale
        else:
            return NLU.DEFAULT_LOCALE

    def __init__(self, locale):
        if not HAS_NLU_DEPENDENCIES:
            raise ImportError(
                "NLU dependencies (padatious, dateparser) are not installed. "
                "Install with: pip install -e .[nlu]"
            )
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.locale = NLU.get_locale(locale)
        self.language = NLU.ENGINES[self.locale]
        self._load_model(self.locale)

    def _load_model(self, locale):
        """Load Padatious intent container and train from YAML files."""
        try:
            locale = NLU.get_locale(locale)
            language = NLU.ENGINES[locale]
            
            basepath = Path(settings.BASE_DIR)
            cache_dir = basepath / "nabd" / "nlu" / f"padatious_cache_{language}"
            cache_dir.mkdir(parents=True, exist_ok=True)
            
            self.container = IntentContainer(str(cache_dir))
            
            # Load all intent files from services
            intent_files = self._discover_intent_files(basepath, language)
            
            # Parse YAML files and add to container
            entities = {}  # Store entities for later use
            
            for intent_file in intent_files:
                with open(intent_file, 'r', encoding='utf-8') as f:
                    content = yaml.safe_load_all(f)
                    for doc in content:
                        if doc is None:
                            continue
                        if doc.get('type') == 'entity':
                            # Store entity for reference
                            entity_name = doc['name']
                            entity_values = doc.get('values', [])
                            entities[entity_name] = entity_values
                            # Add entity to Padatious
                            self.container.add_entity(entity_name, entity_values)
                        elif doc.get('type') == 'intent':
                            intent_name = doc['name']
                            utterances = doc.get('utterances', [])
                            # Convert Snips format to Padatious format
                            converted_utterances = [
                                self._convert_utterance(utt) for utt in utterances
                            ]
                            self.container.add_intent(intent_name, converted_utterances)
            
            # Train the model
            self.container.train(single_thread=True)
            
        except Exception:
            print(traceback.format_exc())

    def _discover_intent_files(self, basepath: Path, language: str):
        """Discover all intent_*.yaml files in service directories."""
        intent_files = []
        
        # Look for */nlu/intent_{language}.yaml
        for service_dir in basepath.iterdir():
            if service_dir.is_dir():
                nlu_dir = service_dir / "nlu"
                if nlu_dir.exists() and nlu_dir.is_dir():
                    intent_file = nlu_dir / f"intent_{language}.yaml"
                    if intent_file.exists():
                        intent_files.append(intent_file)
        
        return intent_files

    def _convert_utterance(self, utterance: str) -> str:
        """
        Convert Snips NLU utterance format to Padatious format.
        
        Snips format: "météo pour [date:snips/datetime](demain)"
        Padatious format: "météo pour {date}"
        """
        import re
        
        # Pattern to match Snips slots: [slotName:entityType](example)
        # We want to extract slotName and replace with {slotName}
        pattern = r'\[([^:]+):[^\]]+\]\([^\)]+\)'
        
        def replace_slot(match):
            slot_name = match.group(1)
            return f"{{{slot_name}}}"
        
        converted = re.sub(pattern, replace_slot, utterance)
        return converted

    async def interpret(self, string: str) -> Optional[Dict[str, Any]]:
        """
        Interpret string from ASR.
        Return None if interpretation failed.
        Returns dict with 'intent' key and slot keys, compatible with Snips format.
        """
        future = self.executor.submit(lambda s=string: self._interpret(s))
        return future.result()

    def _interpret(self, string: str) -> Optional[Dict[str, Any]]:
        """
        Internal interpretation method.
        Converts Padatious output to Snips-compatible format.
        """
        try:
            if string == "":
                return None
            
            # Get intent from Padatious
            intent = self.container.calc_intent(string)
            
            # Check confidence threshold (0.5 is a reasonable default)
            if intent.conf < 0.5:
                return None
            
            result = {"intent": intent.name}
            
            # Extract slots
            if intent.matches:
                for slot_name, slot_value in intent.matches.items():
                    # Special handling for datetime slots
                    if slot_name == "date":
                        parsed_date = self._parse_datetime(
                            slot_value, 
                            languages=[self.language]
                        )
                        if parsed_date:
                            result[slot_name] = parsed_date
                        else:
                            result[slot_name] = slot_value
                    else:
                        result[slot_name] = slot_value
            
            return result
            
        except Exception:
            print(traceback.format_exc())
            return None

    def _parse_datetime(self, text: str, languages: list) -> Optional[str]:
        """
        Parse datetime expressions to Snips-compatible ISO format.
        Returns: "YYYY-MM-DD HH:MM:SS +00:00" or None
        """
        try:
            if dateparser is None:
                return None
                
            # Use dateparser to parse natural language dates
            parsed = dateparser.parse(
                text,
                languages=languages,
                settings={
                    'PREFER_DATES_FROM': 'future',
                    'RETURN_AS_TIMEZONE_AWARE': True,
                    'TIMEZONE': 'UTC'
                }
            )
            
            if parsed:
                # Format to match Snips output: "YYYY-MM-DD HH:MM:SS +00:00"
                # Always use midnight for dates without time
                formatted = parsed.replace(
                    hour=0, minute=0, second=0, microsecond=0
                ).strftime("%Y-%m-%d %H:%M:%S +00:00")
                return formatted
            
            return None
            
        except Exception:
            print(traceback.format_exc())
            return None
