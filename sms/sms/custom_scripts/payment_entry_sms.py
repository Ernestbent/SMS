import frappe
from sms.sms.custom_scripts.sms import get_sms_settings, notify_alert, send_sms_to_customer


def send_payment_entry_sms(doc, method):
    """
    Send SMS on Payment Entry submission
    """
    try:
        # Verify SMS Settings are configured
        settings = get_sms_settings()
        
        if not settings.username or not settings.api_key:
            frappe.log_error(
                "SMS Settings Configuration is incomplete. Please configure username and API Key.",
                "SMS Configuration Error"
            )
            notify_alert("SMS Settings not configured. Please setup SMS gateway credentials.", "red")
            return

        party_name = doc.party_name

        message = (
            f"Dear {party_name}, payment of UGX {doc.paid_amount:,.0f}/= has been processed. "
            f"Reference: {doc.reference_no}. Autozone Professional Limited"
        )
        
        # Send SMS to party
        result = send_sms_to_customer(party_name, message, sender_id=None)

        if result.get("status") == "sent":
            frappe.logger().info(f"SMS sent for Payment Entry {doc.name}: {result}")
            notify_alert("Payment confirmation SMS sent successfully", "green")
        elif result.get("status") == "skipped":
            frappe.logger().info(f"SMS skipped for Payment Entry {doc.name}: {result}")
        else:
            frappe.log_error(
                f"Failed to send SMS for Payment Entry {doc.name}: {result.get('reason')}",
                "SMS Sending Failed",
            )
            notify_alert(result.get("reason"), "red")
        
    except Exception as e:
        error_msg = f"Failed to send SMS for Payment Entry {doc.name}: {str(e)}"
        frappe.log_error(error_msg, "SMS Sending Failed")
        notify_alert(error_msg, "red")
