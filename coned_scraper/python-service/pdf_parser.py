"""
PDF Parser for Con Edison Bills.
Extracts billing data from Con Edison PDF bills including:
- Due date
- Total from billing period
- Balance from previous bill
- kWh usage and cost breakdown
- Supply and delivery charges
"""
import re
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


def parse_coned_bill_pdf(pdf_path: str) -> Dict[str, Any]:
    """
    Parse a Con Edison bill PDF and extract billing data.
    
    Returns dict with:
    - due_date: str (e.g., "Mar 12, 2026")
    - total_from_billing_period: float
    - balance_from_previous_bill: float (0 if none)
    - total_amount_due: float
    - kwh_used: float
    - billing_period_start: str
    - billing_period_end: str
    - billing_days: int
    - supply_charges: dict (breakdown)
    - delivery_charges: dict (breakdown)
    - kwh_cost: float (total_amount / kwh_used)
    - electricity_total: float
    """
    try:
        import pdfplumber
    except ImportError:
        logger.error("pdfplumber not installed. Run: pip install pdfplumber")
        return {"error": "pdfplumber not installed"}
    
    result = {
        "due_date": None,
        "total_from_billing_period": None,
        "balance_from_previous_bill": 0.0,
        "total_amount_due": None,
        "kwh_used": None,
        "billing_period_start": None,
        "billing_period_end": None,
        "billing_days": None,
        "supply_charges": {},
        "delivery_charges": {},
        "kwh_cost": None,
        "electricity_total": None,
        "parsed_at": datetime.utcnow().isoformat() + "Z",
    }
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            # Parse page 1 for summary info
            if len(pdf.pages) >= 1:
                page1_text = pdf.pages[0].extract_text() or ""
                _parse_page1(page1_text, result)
            
            # Parse page 2 for detailed charges
            if len(pdf.pages) >= 2:
                page2_text = pdf.pages[1].extract_text() or ""
                _parse_page2(page2_text, result)
        
        # Calculate kWh cost (cost per kWh)
        if result["electricity_total"] and result["kwh_used"] and result["kwh_used"] > 0:
            result["kwh_cost"] = round(result["electricity_total"] / result["kwh_used"], 4)
        elif result["total_from_billing_period"] and result["kwh_used"] and result["kwh_used"] > 0:
            result["kwh_cost"] = round(result["total_from_billing_period"] / result["kwh_used"], 4)
        
        logger.info(f"Parsed bill PDF: {pdf_path}")
        return result
        
    except Exception as e:
        logger.error(f"Failed to parse PDF {pdf_path}: {e}")
        return {"error": str(e)}


def _parse_page1(text: str, result: Dict[str, Any]):
    """Parse page 1 for summary data."""
    lines = text.split('\n')
    full_text = text
    
    # Due date: "please pay the total amount due by Mar 12, 2026"
    due_date_match = re.search(
        r'please pay the total amount due by\s+([A-Za-z]+\.?\s+\d{1,2},?\s+\d{4})',
        full_text,
        re.IGNORECASE
    )
    if due_date_match:
        result["due_date"] = due_date_match.group(1).strip()
    
    # Alternative due date format: "Due Upon Receipt" or specific date
    if not result["due_date"]:
        due_match = re.search(r'Due\s+(Upon\s+Receipt|[A-Za-z]+\s+\d{1,2},?\s+\d{4})', full_text, re.IGNORECASE)
        if due_match:
            result["due_date"] = due_match.group(1).strip()
    
    # Total from this billing period
    billing_period_match = re.search(
        r'Total from this billing period\s*\$?([\d,]+\.?\d*)',
        full_text,
        re.IGNORECASE
    )
    if billing_period_match:
        result["total_from_billing_period"] = _parse_amount(billing_period_match.group(1))
    
    # Balance from previous bill
    balance_match = re.search(
        r'Balance from previous bill\s*\$?([\d,]+\.?\d*)',
        full_text,
        re.IGNORECASE
    )
    if balance_match:
        result["balance_from_previous_bill"] = _parse_amount(balance_match.group(1))
    
    # Total amount due
    total_due_match = re.search(
        r'Total amount due\s*\$?([\d,]+\.?\d*)',
        full_text,
        re.IGNORECASE
    )
    if total_due_match:
        result["total_amount_due"] = _parse_amount(total_due_match.group(1))
    
    # Billing period: "Billing period: Jan 15, 2026 to Feb 17, 2026"
    period_match = re.search(
        r'Billing period:?\s*([A-Za-z]+\.?\s+\d{1,2},?\s+\d{4})\s+to\s+([A-Za-z]+\.?\s+\d{1,2},?\s+\d{4})',
        full_text,
        re.IGNORECASE
    )
    if period_match:
        result["billing_period_start"] = period_match.group(1).strip()
        result["billing_period_end"] = period_match.group(2).strip()
    
    # Billing days: "(33 days)" or "for 33 days"
    days_match = re.search(r'\(?\s*(\d+)\s*days\s*\)?', full_text, re.IGNORECASE)
    if days_match:
        result["billing_days"] = int(days_match.group(1))


def _parse_page2(text: str, result: Dict[str, Any]):
    """Parse page 2 for detailed charge breakdown."""
    lines = text.split('\n')
    full_text = text
    
    # Extract kWh from meter reading or supply line
    # "Supply 1744.00 kWh" or "Total Usage kWh 1,744"
    kwh_match = re.search(r'(?:Supply|Total Usage|Read Diff)\s*([\d,]+\.?\d*)\s*(?:kWh)?', full_text, re.IGNORECASE)
    if kwh_match:
        result["kwh_used"] = _parse_amount(kwh_match.group(1))
    
    # Alternative: Look for kWh in table header area
    if not result["kwh_used"]:
        kwh_alt = re.search(r'(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*kWh', full_text)
        if kwh_alt:
            result["kwh_used"] = _parse_amount(kwh_alt.group(1))
    
    # Parse Supply Charges section
    supply_charges = {}
    
    # Supply kWh charge: "Supply 1744.00 kWh @13.251¢/kWh $231.10"
    supply_kwh_match = re.search(
        r'Supply\s+([\d,]+\.?\d*)\s*kWh\s*@([\d.]+)[¢c]/kWh\s*\$?([\d,]+\.?\d*)',
        full_text,
        re.IGNORECASE
    )
    if supply_kwh_match:
        supply_charges["supply_kwh"] = _parse_amount(supply_kwh_match.group(1))
        supply_charges["supply_rate_cents"] = float(supply_kwh_match.group(2))
        supply_charges["supply_charge"] = _parse_amount(supply_kwh_match.group(3))
        if not result["kwh_used"]:
            result["kwh_used"] = supply_charges["supply_kwh"]
    
    # Merchant Function Charge
    merchant_match = re.search(r'Merchant Function Charge\s*\$?([\d,]+\.?\d*)', full_text, re.IGNORECASE)
    if merchant_match:
        supply_charges["merchant_function_charge"] = _parse_amount(merchant_match.group(1))
    
    # GRT & other tax surcharges (supply side - first occurrence before "Total electricity supply")
    supply_section = re.search(r'Your Supply Charges(.+?)Total electricity supply charges', full_text, re.DOTALL | re.IGNORECASE)
    if supply_section:
        supply_text = supply_section.group(1)
        grt_match = re.search(r'GRT & other tax surcharges\s*\$?([\d,]+\.?\d*)', supply_text, re.IGNORECASE)
        if grt_match:
            supply_charges["grt_tax_surcharges"] = _parse_amount(grt_match.group(1))
        
        # Sales tax (supply side)
        sales_tax_match = re.search(r'Sales tax @([\d.]+)%\s*\$?([\d,]+\.?\d*)', supply_text, re.IGNORECASE)
        if sales_tax_match:
            supply_charges["sales_tax_rate"] = float(sales_tax_match.group(1))
            supply_charges["sales_tax"] = _parse_amount(sales_tax_match.group(2))
    
    # Total electricity supply charges
    total_supply_match = re.search(
        r'Total electricity supply charges\s*\$?([\d,]+\.?\d*)',
        full_text,
        re.IGNORECASE
    )
    if total_supply_match:
        supply_charges["total"] = _parse_amount(total_supply_match.group(1))
    
    result["supply_charges"] = supply_charges
    
    # Parse Delivery Charges section
    delivery_charges = {}
    
    # Basic service charge
    basic_match = re.search(r'Basic service charge\s*\$?([\d,]+\.?\d*)', full_text, re.IGNORECASE)
    if basic_match:
        delivery_charges["basic_service_charge"] = _parse_amount(basic_match.group(1))
    
    # Delivery kWh charge: "Delivery 1744.00 kWh @16.982¢/kWh $296.17"
    delivery_kwh_match = re.search(
        r'Delivery\s+([\d,]+\.?\d*)\s*kWh\s*@([\d.]+)[¢c]/kWh\s*\$?([\d,]+\.?\d*)',
        full_text,
        re.IGNORECASE
    )
    if delivery_kwh_match:
        delivery_charges["delivery_kwh"] = _parse_amount(delivery_kwh_match.group(1))
        delivery_charges["delivery_rate_cents"] = float(delivery_kwh_match.group(2))
        delivery_charges["delivery_charge"] = _parse_amount(delivery_kwh_match.group(3))
    
    # System Benefit Charge
    sbc_match = re.search(
        r'System Benefit Charge\s*@?([\d.]+)?[¢c]?/?kWh\s*\$?([\d,]+\.?\d*)',
        full_text,
        re.IGNORECASE
    )
    if sbc_match:
        if sbc_match.group(1):
            delivery_charges["system_benefit_rate_cents"] = float(sbc_match.group(1))
        delivery_charges["system_benefit_charge"] = _parse_amount(sbc_match.group(2))
    
    # Delivery section GRT and sales tax
    delivery_section = re.search(r'Your Delivery Charges(.+?)Total electricity delivery charges', full_text, re.DOTALL | re.IGNORECASE)
    if delivery_section:
        delivery_text = delivery_section.group(1)
        grt_match = re.search(r'GRT & other tax surcharges\s*\$?([\d,]+\.?\d*)', delivery_text, re.IGNORECASE)
        if grt_match:
            delivery_charges["grt_tax_surcharges"] = _parse_amount(grt_match.group(1))
        
        sales_tax_match = re.search(r'Sales tax @([\d.]+)%\s*\$?([\d,]+\.?\d*)', delivery_text, re.IGNORECASE)
        if sales_tax_match:
            delivery_charges["sales_tax_rate"] = float(sales_tax_match.group(1))
            delivery_charges["sales_tax"] = _parse_amount(sales_tax_match.group(2))
    
    # Total electricity delivery charges
    total_delivery_match = re.search(
        r'Total electricity delivery charges\s*\$?([\d,]+\.?\d*)',
        full_text,
        re.IGNORECASE
    )
    if total_delivery_match:
        delivery_charges["total"] = _parse_amount(total_delivery_match.group(1))
    
    result["delivery_charges"] = delivery_charges
    
    # Your electricity total
    elec_total_match = re.search(
        r'Your electricity total\s*\$?([\d,]+\.?\d*)',
        full_text,
        re.IGNORECASE
    )
    if elec_total_match:
        result["electricity_total"] = _parse_amount(elec_total_match.group(1))


def _parse_amount(amount_str: str) -> float:
    """Parse a currency amount string to float."""
    if not amount_str:
        return 0.0
    cleaned = re.sub(r'[,$]', '', amount_str.strip())
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def extract_billing_period_dates(period_str: str) -> Optional[tuple]:
    """
    Parse billing period string like "Jan 15, 2026 to Feb 17, 2026"
    Returns (start_date, end_date) as datetime objects or None.
    """
    match = re.search(
        r'([A-Za-z]+\.?\s+\d{1,2},?\s+\d{4})\s+to\s+([A-Za-z]+\.?\s+\d{1,2},?\s+\d{4})',
        period_str,
        re.IGNORECASE
    )
    if not match:
        return None
    
    formats = ["%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y"]
    start_str = match.group(1).replace(',', '')
    end_str = match.group(2).replace(',', '')
    
    start_date = None
    end_date = None
    
    for fmt in formats:
        try:
            start_date = datetime.strptime(start_str, fmt)
            break
        except ValueError:
            continue
    
    for fmt in formats:
        try:
            end_date = datetime.strptime(end_str, fmt)
            break
        except ValueError:
            continue
    
    if start_date and end_date:
        return (start_date, end_date)
    return None
