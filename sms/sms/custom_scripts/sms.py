import frappe
import requests
from sms.sms.utils.utils import get_customer_number


def get_sms_settings():
    return frappe.get_single("SMS Settings Configurations")


def notify_alert(message, indicator="blue"):
    frappe.publish_realtime(
        "msgprint",
        {
            "message": message,
            "indicator": indicator,
            "alert": True,
        },
        user=frappe.session.user,
        after_commit=True,
    )


def send_sms(number, message, sender_id=None):
    """
    Send SMS directly to a number
    """

    if not number or not message:
        error = "Invalid number or message"
        frappe.log_error(error, "SMS Validation Error")
        return {"status": "failed", "reason": error}

    try:
        settings = get_sms_settings()
    except Exception as e:
        error = "SMS Settings Configuration not found. Please create SMS Settings Configurations."
        frappe.log_error(str(e), error)
        return {"status": "failed", "reason": error}

    if not settings.username or not settings.api_key:
        error = "SMS Settings incomplete. Username and API Key are required."
        frappe.log_error(error, "SMS Configuration Error")
        return {"status": "failed", "reason": error}

    # use sender_id from settings if not passed
    sender_id = sender_id or settings.sender_id

    url = "https://comms.egosms.co/api/v1/json/"

    payload = {
        "method": "SendSms",
        "userdata": {
            "username": settings.username,
            "password": settings.api_key
        },
        "msgdata": [
            {
                "number": number,
                "message": message,
                "senderid": sender_id,
                "priority": "0"
            }
        ]
    }

    headers = {
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=20)
        
        # Log the response for debugging
        frappe.logger().info(f"SMS API Response Status: {response.status_code}")
        frappe.logger().info(f"SMS API Response Body: {response.text}")
        
        # Check for HTTP errors
        if response.status_code != 200:
            error_msg = f"SMS API returned status {response.status_code}: {response.text}"
            frappe.log_error(error_msg, "SMS API Error")
            return {"status": "failed", "reason": error_msg}

        return {"status": "sent", "response": response.text}

    except requests.exceptions.Timeout:
        error = "SMS sending timeout. API did not respond within 20 seconds."
        frappe.log_error(error, "SMS Timeout")
        return {"status": "failed", "reason": error}
    
    except requests.exceptions.ConnectionError as e:
        error = f"Cannot connect to SMS gateway: {str(e)}"
        frappe.log_error(error, "SMS Connection Error")
        return {"status": "failed", "reason": error}
    
    except Exception as e:
        error = f"SMS sending failed: {str(e)}"
        frappe.log_error(error, "SMS Sending Error")
        return {"status": "failed", "reason": error}


def send_sms_to_customer(customer_name, message, sender_id=None):
    """
    High-level function: send SMS using Customer doctype
    """

    customer = None

    if customer_name and frappe.db.exists("Customer", customer_name):
        customer = frappe.get_doc("Customer", customer_name)
    elif customer_name:
        customer_docname = frappe.db.get_value(
            "Customer",
            {"customer_name": customer_name},
            "name",
        )
        if customer_docname:
            customer = frappe.get_doc("Customer", customer_docname)

    if not customer:
        reason = f"Customer {customer_name} not found"
        frappe.log_error(reason, "SMS Error")
        return {"status": "skipped", "reason": reason}

    mobile_no = customer.get("mobile_no")
    number = get_customer_number(customer_name, customer)

    if not number:
        frappe.log_error(f"No valid phone number for {customer_name}", "SMS Error")
        return {"status": "failed", "reason": "No valid mobile_no"}

    return send_sms(number, message, sender_id)


def send_sales_order_sms(doc, method):
    """
    Send SMS on Sales Order submission
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

        # Get customer phone number
        customer_name = doc.customer
        message = f"""
                Dear {customer_name}, your order {doc.name} has been received successfully. Amount: /= {doc.grand_total:,.0f}. We are processing it and will update you shortly. Thank you for choosing us.
                Autozone Professional Limited
                """
        
        # Send SMS to customer
        result = send_sms_to_customer(customer_name, message, sender_id=None)

        if result.get("status") == "sent":
            frappe.logger().info(f"SMS sent for SO {doc.name}: {result}")
            notify_alert("SMS notification sent successfully", "green")
        elif result.get("status") == "skipped":
            frappe.logger().info(f"SMS skipped for SO {doc.name}: {result}")
        else:
            frappe.log_error(
                f"Failed to send SMS for Sales Order {doc.name}: {result.get('reason')}",
                "SMS Sending Failed",
            )
            notify_alert(result.get("reason"), "red")
        
    except Exception as e:
        error_msg = f"Failed to send SMS for Sales Order {doc.name}: {str(e)}"
        frappe.log_error(error_msg, "SMS Sending Failed")
        notify_alert(error_msg, "red")
