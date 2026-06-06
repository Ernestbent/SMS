import frappe
import requests
from sms.sms.utils.utils import get_customer_number


def get_sms_settings():
    return frappe.get_single("SMS Settings Configurations")


def send_sms(number, message, sender_id=None):
    """
    Send SMS directly to a number
    """

    if not number or not message:
        error = "Invalid number or message"
        frappe.log_error(error, "SMS Validation Error")
        return error

    try:
        settings = get_sms_settings()
    except Exception as e:
        error = "SMS Settings Configuration not found. Please create SMS Settings Configurations."
        frappe.log_error(str(e), error)
        return error

    if not settings.username or not settings.api_key:
        error = "SMS Settings incomplete. Username and API Key are required."
        frappe.log_error(error, "SMS Configuration Error")
        return error

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
            return error_msg
        
        return response.text

    except requests.exceptions.Timeout:
        error = "SMS sending timeout. API did not respond within 20 seconds."
        frappe.log_error(error, "SMS Timeout")
        return error
    
    except requests.exceptions.ConnectionError as e:
        error = f"Cannot connect to SMS gateway: {str(e)}"
        frappe.log_error(error, "SMS Connection Error")
        return error
    
    except Exception as e:
        error = f"SMS sending failed: {str(e)}"
        frappe.log_error(error, "SMS Sending Error")
        return error


def send_sms_to_customer(customer_name, message, sender_id=None):
    """
    High-level function: send SMS using Customer doctype
    """

    number = get_customer_number(customer_name)

    if not number:
        frappe.log_error(f"No valid phone number for {customer_name}", "SMS Error")
        return "No valid number"

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
            frappe.msgprint(
                "SMS Settings not configured. Please setup SMS gateway credentials.",
                title="SMS Error",
                indicator="red"
            )
            return

        # Get customer phone number
        customer_name = doc.customer
        message = f"""
                Dear {customer_name}, your order {doc.name} has been received successfully. Amount: /= {doc.grand_total:,.0f}. We are processing it and will update you shortly. Thank you for choosing us.
                Autozone Professional Limited
                """
        
        # Send SMS to customer
        result = send_sms_to_customer(customer_name, message, sender_id=None)
        
        # Log the result for debugging
        frappe.logger().info(f"SMS sent for SO {doc.name}: {result}")
        frappe.msgprint(f"SMS notification sent successfully", title="SMS Sent", indicator="green")
        
    except Exception as e:
        error_msg = f"Failed to send SMS for Sales Order {doc.name}: {str(e)}"
        frappe.log_error(error_msg, "SMS Sending Failed")
        frappe.msgprint(error_msg, title="SMS Error", indicator="red")