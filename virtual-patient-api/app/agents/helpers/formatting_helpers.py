"""
Helper functions for formatting data structures
"""

from typing import Dict, Any


def format_demographics(data: Dict[str, Any]) -> str:
    """Format demographic information"""
    formatted = ""
    if "age" in data and data["age"] is not None:
        formatted += f"Age: {data['age']}\n"
    if "weight_in_kg" in data and data["weight_in_kg"] is not None:
        formatted += f"Weight: {data['weight_in_kg']} kg\n"
    return formatted


def format_simple_field(data: Dict[str, Any], field_name: str, label: str) -> str:
    """Format a simple field with label"""
    if field_name in data and data[field_name] is not None and data[field_name] != "":
        return f"{label}: {data[field_name]}\n"
    return ""


def format_dict_field(data: Dict[str, Any], field_name: str, label: str) -> str:
    """Format a dictionary field"""
    if field_name not in data or not data[field_name]:
        return f"{label}: Not specified\n"
    
    field_data = data[field_name]
    if isinstance(field_data, dict):
        parts = []
        for key, value in field_data.items():
            if value is not None and value != "":
                parts.append(f"{key}: {value}")
        if parts:
            return f"{label}: {', '.join(parts)}\n"
        else:
            return f"{label}: Not specified\n"
    else:
        return f"{label}: {field_data}\n"


def format_list_field(data: Dict[str, Any], field_name: str, label: str, default_text: str = "Not specified") -> str:
    """Format a list field containing dictionaries or strings"""
    if field_name not in data or not data[field_name]:
        return f"{label}: {default_text}\n"
    
    items = []
    for item in data[field_name]:
        if isinstance(item, dict):
            # Join all non-empty key-value pairs
            parts = []
            for key, value in item.items():
                if value is not None and value != "":
                    parts.append(f"{key}: {value}")
            if parts:
                items.append("; ".join(parts))
            else:
                items.append(f"{label[:-1]} information available")
        else:
            items.append(str(item))
    
    return f"{label}: {', '.join(items)}\n"
