from datetime import timedelta

import frappe
from frappe.utils import flt, getdate, nowdate

from sms.sms.custom_scripts.sms_message import get_sms_settings, send_sms_to_customer
from sms.sms.utils.utils import get_customer_short_name


MINIMUM_OUTSTANDING_AMOUNT = 1000


def send_overdue_invoice_reminders_after_7_days():
    """
    Send one daily SMS per customer with their total for invoices at least 7 days old.
    """
    try:
        settings = get_sms_settings()
    except Exception as e:
        frappe.log_error(
            f"Failed to load SMS settings for invoice reminders: {str(e)}",
            "Invoice Reminder Error",
        )
        return

    if not settings.username or not settings.api_key:
        frappe.log_error(
            "SMS Settings Configuration is incomplete. Please configure username and API Key.",
            "Invoice Reminder Error",
        )
        return

    today = getdate(nowdate())
    reminder_date = today - timedelta(days=7)

    overdue_invoices = frappe.get_all(
        "Sales Invoice",
        filters={
            "docstatus": 1,
            "outstanding_amount": [">", 0],
            "posting_date": ["<=", reminder_date],
        },
        fields=[
            "customer",
            "customer_name",
            "outstanding_amount",
        ],
        order_by="customer asc",
    )

    customer_totals = {}
    for invoice in overdue_invoices:
        customer = customer_totals.setdefault(
            invoice.customer,
            {
                "customer_name": invoice.customer_name or invoice.customer,
                "invoice_count": 0,
                "outstanding_amount": 0,
            },
        )
        customer["invoice_count"] += 1
        customer["outstanding_amount"] += flt(invoice.outstanding_amount)

    for customer_name, outstanding in customer_totals.items():
        try:
            if outstanding["outstanding_amount"] < MINIMUM_OUTSTANDING_AMOUNT:
                frappe.logger().info(
                    f"Outstanding reminder skipped for {customer_name}: "
                    f"balance below UGX {MINIMUM_OUTSTANDING_AMOUNT:,.0f}"
                )
                continue

            customer_display_name = get_customer_short_name(outstanding["customer_name"])
            message = (
                f"Autozone: Dear {customer_display_name}, "
                f"UGX {outstanding['outstanding_amount']:,.0f} is overdue. "
                "Kindly pay as soon as possible. Call 0764376747, 0743045144."
            )

            result = send_sms_to_customer(customer_name, message, sender_id=None)

            if result.get("status") == "sent":
                frappe.logger().info(f"Outstanding reminder sent to {customer_name}: {result}")
            elif result.get("status") == "skipped":
                frappe.logger().info(f"Outstanding reminder skipped for {customer_name}: {result}")
            else:
                frappe.log_error(
                    f"Failed to send outstanding reminder to {customer_name}: {result.get('reason')}",
                    "Invoice Reminder Error",
                )
        except Exception as e:
            frappe.log_error(
                f"Outstanding reminder crashed for {customer_name}: {str(e)}",
                "Invoice Reminder Error",
            )
