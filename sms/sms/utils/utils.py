import re
import frappe


def normalize_ug_number(number):
    """
    Normalize Ugandan phone numbers to 256 format.
    Handles:
    - 0757xxxxxx → 256757xxxxxx
    - +256757xxxxxx → 256757xxxxxx
    - 256757xxxxxx → 256757xxxxxx
    - 7xxxxxxxx → 2567xxxxxxxx
    """

    if not number:
        return None

    # remove spaces, dashes, brackets
    number = re.sub(r"[^\d+]", "", number)

    # remove +
    if number.startswith("+"):
        number = number[1:]

    # 07xxxxxxxx → 2567xxxxxxxx
    if number.startswith("0"):
        number = "256" + number[1:]

    # 7xxxxxxxx → 2567xxxxxxxx (fallback)
    if number.startswith("7") and len(number) == 9:
        number = "256" + number

    # already correct
    if number.startswith("256"):
        return number

    return number


def get_customer_number(customer_name, customer=None):
    """
    SMS should only use mobile_no.
    If a WhatsApp number exists, SMS must be skipped.
    """

    if not customer:
        if not frappe.db.exists("Customer", customer_name):
            return None
        customer = frappe.get_doc("Customer", customer_name)

    return normalize_ug_number(customer.get("mobile_no"))
