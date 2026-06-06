import frappe
from sms.sms.utils.utils import get_customer_number
from sms.sms.custom_scripts.sms import get_sms_settings, send_sms_to_customer


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
            frappe.msgprint(
                "SMS Settings not configured. Please setup SMS gateway credentials.",
                title="SMS Error",
                indicator="red"
            )
            return

        # Get party (customer/supplier) name
        party_name = doc.party_name
        
        # Determine message based on payment type
        if doc.payment_type == "Receive":
            message = f"""
                Dear {party_name}, we have received your payment of {doc.paid_amount:,.0f}/= reference {doc.reference_no}. Thank you for your business.
                Autozone Professional Limited
                """
        else:  # Send payment
            message = f"""
                Dear {party_name}, payment of /= {doc.paid_amount:,.0f} has been processed and will be received. Reference: {doc.reference_no}.
                Autozone Professional Limited
                """
        
        # Send SMS to party
        result = send_sms_to_customer(party_name, message, sender_id=None)
        
        # Log the result for debugging
        frappe.logger().info(f"SMS sent for Payment Entry {doc.name}: {result}")
        frappe.msgprint(f"Payment confirmation SMS sent successfully", title="SMS Sent", indicator="green")
        
    except Exception as e:
        error_msg = f"Failed to send SMS for Payment Entry {doc.name}: {str(e)}"
        frappe.log_error(error_msg, "SMS Sending Failed")
        frappe.msgprint(error_msg, title="SMS Error", indicator="red")
