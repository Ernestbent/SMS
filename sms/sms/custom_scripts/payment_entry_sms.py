import frappe
from sms.sms.custom_scripts.sms_message import get_sms_settings, notify_alert, send_sms_to_customer
from sms.sms.utils.utils import get_customer_short_name

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
        
        # Use customer_display_name (actual customer name) in the message
        message = (
            f"Autozone: Dear {customer_display_name}, payment of UGX "
            f"{doc.paid_amount:,.0f}/= processed. "
            "Call 0743045144 or 0764 376747."
        )
        
        # Send SMS using customer_id (the actual link)
        result = send_sms_to_customer(
            customer_id,  # This is the Customer ID (e.g., CUST-2026-02885)
            message, 
            sender_id=None,
            reference_doctype="Payment Entry",
            reference_name=doc.name
        )

        if result.get("status") == "sent":
            frappe.logger().info(f"SMS sent for Payment Entry {doc.name} to customer {customer_display_name}")
            notify_alert("Payment SMS sent successfully", "green")
        elif result.get("status") == "skipped":
            frappe.logger().info(f"SMS skipped for Payment Entry {doc.name}: {result.get('reason')}")
        else:
            frappe.log_error(
                f"SMS failed for Payment Entry {doc.name}: {result.get('reason')}",
                "SMS Failed",
            )
            notify_alert(f"SMS failed: {result.get('reason')}", "red")
        
    except Exception as e:
        error_msg = f"SMS error for Payment Entry {doc.name}: {str(e)[:100]}"
        frappe.log_error(error_msg, "SMS Error")
        notify_alert("Failed to send payment SMS", "red")
