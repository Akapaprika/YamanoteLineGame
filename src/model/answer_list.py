import csv
from dataclasses import dataclass, field
from typing import Dict, List, Set

from ..utils.text_norm import normalize_text


@dataclass
class AnswerList:
    # items: list of display strings (e.g. "兵庫県-相生市")
    items: List[str] = field(default_factory=list)
    # used: set of display strings that have been marked used
    used: Set[str] = field(default_factory=set)
    # internal maps: display -> match_full (concat of match parts)
    _match_map: Dict[str, str] = field(default_factory=dict)
    # display -> class_key (first match part)
    _class_map: Dict[str, str] = field(default_factory=dict)
    # display -> element_key (last match part)
    _element_map: Dict[str, str] = field(default_factory=dict)
    # display -> (displays_list, matches_list) for original CSV structure preservation
    _display_map: Dict[str, tuple] = field(default_factory=dict)

    @classmethod
    def load_from_csv(cls, path: str, encoding: str = "utf-8") -> "AnswerList":
        """Load CSV with optional separator line (empty row).
        Format: alternating display,match pairs (display in odd columns, match in even columns)
        - Rows before empty line: unanswered items
        - Rows after empty line: answered items (saved state)
        If no empty line found, all rows are unanswered.
        """
        items = []
        match_map = {}
        class_map = {}
        element_map = {}
        display_map = {}
        used = set()
        
        with open(path, newline="", encoding=encoding) as f:
            rows = list(csv.reader(f))
        
        # Find separator (empty row)
        separator_idx = None
        for idx, row in enumerate(rows):
            if not row or all(not cell.strip() for cell in row):
                separator_idx = idx
                break
        
        # Process unanswered items (before separator or all rows if no separator)
        end_idx = separator_idx if separator_idx is not None else len(rows)
        for row in rows[:end_idx]:
            if not row:
                continue
            # Extract display and match parts
            # Pattern: display[0], match[0], display[1], match[1], ...
            displays = [row[i].strip() for i in range(0, len(row), 2) if i < len(row) and row[i].strip()]
            matches = [row[i].strip() for i in range(1, len(row), 2) if i < len(row) and row[i].strip()]
            if not (displays and matches):
                continue
            # Construct normalized key: display parts joined with '-'
            norm_disp = normalize_text('-'.join(displays))
            if not norm_disp:
                continue
            norm_match = normalize_text(''.join(matches))
            items.append(norm_disp)
            match_map[norm_disp] = norm_match
            class_map[norm_disp] = normalize_text(matches[0])
            element_map[norm_disp] = normalize_text(matches[-1])
            # Store original structure for later reconstruction
            display_map[norm_disp] = (displays, matches)
        
        # Process answered items (after separator if present)
        if separator_idx is not None:
            for row in rows[separator_idx + 1:]:
                if not row:
                    continue
                displays = [row[i].strip() for i in range(0, len(row), 2) if i < len(row) and row[i].strip()]
                matches = [row[i].strip() for i in range(1, len(row), 2) if i < len(row) and row[i].strip()]
                if not (displays and matches):
                    continue
                norm_disp = normalize_text('-'.join(displays))
                if not norm_disp:
                    continue
                norm_match = normalize_text(''.join(matches))
                # Add to items list if not already present
                if norm_disp not in items:
                    items.append(norm_disp)
                    match_map[norm_disp] = norm_match
                    class_map[norm_disp] = normalize_text(matches[0])
                    element_map[norm_disp] = normalize_text(matches[-1])
                # Store original structure if not already stored
                if norm_disp not in display_map:
                    display_map[norm_disp] = (displays, matches)
                # Mark as used
                used.add(norm_disp)
        
        obj = cls(items=items, used=used)
        obj._match_map = match_map
        obj._class_map = class_map
        obj._element_map = element_map
        obj._display_map = display_map
        return obj

    def contains(self, text: str, previous_class: str = None) -> bool:
        """Check if text matches any unused item (full or short form)."""
        return self.find_match(text, previous_class) is not None

    def find_match(self, text: str, previous_class: str = None):
        """Return the first matching unused display key for given input text, or None.

        Supports:
        1. Full match (match_map): matches the complete normalized element text
           (prefecture + city reading combined)
        2. Short-form match (element_map): matches only the city reading when
           previous_class matches the class_map of the candidate (same prefecture
           as the last answered item)
        
        Note: For suggest format matching (text in parentheses), use the extraction
        logic in host_submit_answer before calling this method.
        """
        t = normalize_text(text)
        for disp in self.items:
            if disp in self.used:
                continue
            # Full match: text normalized matches the entire concatenated matches
            # (prefecture reading + city reading)
            if t == self._match_map.get(disp):
                return disp
            # Short-form match: when previous class is known, match just the element
            # (city reading) only if the previous prefecture matches this item's prefecture
            if (previous_class and t == self._element_map.get(disp) and
                    previous_class == self._class_map.get(disp)):
                return disp
        return None

    def mark_used(self, text: str, previous_class: str = None):
        """Mark first matching unused item as used and return the display key.

        Returns the matched display key or None if no match.
        """
        matched = self.find_match(text, previous_class)
        if matched:
            self.used.add(matched)
            return matched
        return None

    def remaining_count(self) -> int:
        return len([i for i in self.items if i not in self.used])

    def all_items(self) -> List[str]:
        return list(self.items)

    def save_to_csv(self, path: str, encoding: str = "utf-8") -> None:
        """Save current state to CSV with empty row separator.
        Unanswered items before separator, answered items after.
        Preserves original classification structure using _display_map.
        """
        with open(path, "w", newline="", encoding=encoding) as f:
            writer = csv.writer(f)
            # Write unanswered items
            for norm_disp in self.items:
                if norm_disp not in self.used:
                    if norm_disp in self._display_map:
                        displays, matches = self._display_map[norm_disp]
                        # Reconstruct original row: display[0], match[0], display[1], match[1], ...
                        row = []
                        for d, m in zip(displays, matches):
                            row.extend([d, m])
                        writer.writerow(row)
                    else:
                        # Fallback if _display_map missing (shouldn't happen)
                        writer.writerow([norm_disp, self._match_map.get(norm_disp, "")])
            # Write separator (empty row)
            writer.writerow([])
            # Write answered items
            for norm_disp in self.items:
                if norm_disp in self.used:
                    if norm_disp in self._display_map:
                        displays, matches = self._display_map[norm_disp]
                        # Reconstruct original row: display[0], match[0], display[1], match[1], ...
                        row = []
                        for d, m in zip(displays, matches):
                            row.extend([d, m])
                        writer.writerow(row)
                    else:
                        # Fallback if _display_map missing (shouldn't happen)
                        writer.writerow([norm_disp, self._match_map.get(norm_disp, "")])