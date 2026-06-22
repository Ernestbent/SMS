import frappe
from frappe.utils import formatdate, getdate, nowdate

from sms.sms.custom_scripts.sms import get_sms_settings, send_sms_to_customer
from sms.sms.utils.utils import append_inquiry_contacts, get_customer_short_name


def send_weekly_payment_reminders():
    """
    Send weekly SMS reminders for overdue unpaid Sales Invoices.
    """
    try:
        settings = get_sms_settings()
    except Exception as e:
        frappe.log_error(
            f"Failed to load SMS settings for payment reminders: {str(e)}",
            "Payment Reminder Error",
        )
        return

    if not settings.username or not settings.api_key:
        frappe.log_error(
            "SMS Settings Configuration is incomplete. Please configure username and API Key.",
            "Payment Reminder Error",
        )
        return

    overdue_invoices = frappe.get_all(
        "Sales Invoice",
        filters={
            "docstatus": 1,
            "outstanding_amount": [">", 0],
            "due_date": ["<=", nowdate()],
        },
        fields=[
            "name",
            "customer",
            "customer_name",
            "outstanding_amount",
            "due_date",
            "grand_total",
        ],
        order_by="due_date asc",
    )

    for invoice in overdue_invoices:
        try:
            customer_name = invoice.customer
            customer_display_name = get_customer_short_name(invoice.customer_name or customer_name)

            message = (
                f"Dear {customer_display_name}, this is a reminder that invoice {invoice.name} "
                f"for UGX {invoice.outstanding_amount:,.0f} is still unpaid and was due on "
                f"{formatdate(getdate(invoice.due_date))}. Please make payment at your earliest convenience. "
                "Thank you, Autozone Professional Limited."
            )
            message = append_inquiry_contacts(message)

            result = send_sms_to_customer(customer_name, message, sender_id=None)

            if result.get("status") == "sent":
                frappe.logger().info(f"Weekly payment reminder sent for {invoice.name}: {result}")
            elif result.get("status") == "skipped":
                frappe.logger().info(f"Weekly payment reminder skipped for {invoice.name}: {result}")
            else:
                frappe.log_error(
                    f"Failed to send weekly payment reminder for {invoice.name}: {result.get('reason')}",
                    "Payment Reminder Error",
                )
        except Exception as e:
            frappe.log_error(
                f"Weekly payment reminder crashed for {invoice.name}: {str(e)}",
                "Payment Reminder Error",
            )
