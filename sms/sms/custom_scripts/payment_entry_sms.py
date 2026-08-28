import frappe
from sms.sms.custom_scripts.sms_message import get_sms_settings, notify_alert, send_sms_to_customer
from sms.sms.utils.utils import get_customer_short_name


def get_payment_messages(customer_display_name, paid_amount, region):
    messages = [
        (
            "English",
            (
                f"Autozone: Mr/Ms {customer_display_name}, payment of UGX "
                f"{paid_amount:,.0f}/= has been received. Thank you"
            ),
        )
    ]

    if str(region or "").strip().casefold() == "central":
        messages.append(
            (
                "Luganda",
                (
                    f"Autozone: Mr/Ms {customer_display_name}, tweyanziza, tukutegeza nti "
                    f"okusasula kwa UGX {paid_amount:,.0f}/= kufuniddwa."
                ),
            )
        )

    return messages


def send_payment_entry_sms(doc, method):
    """
    Send SMS on Payment Entry submission
    """
    try:
        # Only send SMS for Customer payments
        if doc.party_type != "Customer":
            frappe.logger().info(f"Payment Entry {doc.name} is for {doc.party_type}, skipping SMS")
            return
        
        # Verify SMS Settings are configured
        settings = get_sms_settings()
        
        if not settings.username or not settings.api_key:
            frappe.log_error(
                "SMS Settings incomplete",
                "SMS Configuration Error"
            )
            notify_alert("SMS Settings not configured", "red")
            return

        # Use 'party' as the link to the Customer document
        customer_id = doc.party  # This is the Customer ID (link field)

        # Validate that we have a valid Customer link
        if not customer_id:
            frappe.log_error(
                f"Payment Entry {doc.name} has no Customer linked",
                "Invalid Payment Entry"
            )
            notify_alert("Cannot send SMS: No Customer linked to this Payment Entry", "red")
            return

        # Get the actual customer document to get the correct display name
        customer_doc = frappe.get_doc("Customer", customer_id)
        customer_display_name = get_customer_short_name(customer_doc.customer_name or customer_id)
        messages = get_payment_messages(
            customer_display_name,
            doc.paid_amount,
            customer_doc.get("region"),
        )

        sent_count = 0
        skipped_count = 0
        for language, message in messages:
            result = send_sms_to_customer(
                customer_id,
                message,
                sender_id=None,
                reference_doctype="Payment Entry",
                reference_name=doc.name,
            )

            if result.get("status") == "sent":
                sent_count += 1
                frappe.logger().info(
                    f"{language} SMS sent for Payment Entry {doc.name} "
                    f"to customer {customer_display_name}"
                )
            elif result.get("status") == "skipped":
                skipped_count += 1
                frappe.logger().info(
                    f"{language} SMS skipped for Payment Entry {doc.name}: "
                    f"{result.get('reason')}"
                )
            else:
                frappe.log_error(
                    f"{language} SMS failed for Payment Entry {doc.name}: "
                    f"{result.get('reason')}",
                    "SMS Failed",
                )

        if sent_count == len(messages):
            notify_alert("Payment SMS sent successfully", "green")
        elif sent_count:
            notify_alert(f"Only {sent_count} of {len(messages)} payment SMS messages sent", "orange")
        elif skipped_count != len(messages):
            notify_alert("Payment SMS failed", "red")
        
    except Exception as e:
        error_msg = f"SMS error for Payment Entry {doc.name}: {str(e)[:100]}"
        frappe.log_error(error_msg, "SMS Error")
        notify_alert("Failed to send payment SMS", "red")
