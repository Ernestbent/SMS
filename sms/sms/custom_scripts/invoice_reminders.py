from datetime import timedelta

import frappe
from frappe.utils import getdate, nowdate

from sms.sms.custom_scripts.sms import get_sms_settings, send_sms_to_customer


def send_overdue_invoice_reminders_after_7_days():
    """
    Send a single SMS reminder for unpaid Sales Invoices that are 7 days overdue.
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

    reminder_date = getdate(nowdate()) - timedelta(days=7)

    overdue_invoices = frappe.get_all(
        "Sales Invoice",
        filters={
            "docstatus": 1,
            "outstanding_amount": [">", 0],
            "due_date": reminder_date,
        },
        fields=[
            "name",
            "customer",
            "customer_name",
            "outstanding_amount",
            "due_date",
        ],
        order_by="due_date asc",
    )

    for invoice in overdue_invoices:
        try:
            customer_name = invoice.customer
            customer_display_name = invoice.customer_name or customer_name
            days_overdue = (getdate(nowdate()) - getdate(invoice.due_date)).days
            day_label = "day" if days_overdue == 1 else "days"

            message = (
                f"Dear {customer_display_name}, invoice {invoice.name} is {days_overdue} {day_label} overdue. "
                "Please pay as soon as possible. Autozone Professional Limited."
            )

            result = send_sms_to_customer(customer_name, message, sender_id=None)

            if result.get("status") == "sent":
                frappe.logger().info(f"7-day overdue reminder sent for {invoice.name}: {result}")
            elif result.get("status") == "skipped":
                frappe.logger().info(f"7-day overdue reminder skipped for {invoice.name}: {result}")
            else:
                frappe.log_error(
                    f"Failed to send 7-day overdue reminder for {invoice.name}: {result.get('reason')}",
                    "Invoice Reminder Error",
                )
        except Exception as e:
            frappe.log_error(
                f"7-day overdue reminder crashed for {invoice.name}: {str(e)}",
                "Invoice Reminder Error",
            )
