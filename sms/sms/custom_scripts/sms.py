import frappe
import requests
from sms.sms.utils.utils import append_inquiry_contacts, get_customer_number, get_customer_short_name
from datetime import datetime


def get_sms_settings():
	## Get SMS configuration
	return frappe.get_single("SMS Settings Configurations")


def notify_alert(message, indicator="blue"):
	## Send real-time alert notification
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


def create_message_record(customer, message, status="sent", reference_doctype=None, reference_name=None):
	## Create Message record - customer_name auto-fetches via fetch_from
	try:
		if not frappe.db.exists("Customer", customer):
			frappe.log_error(f"Customer {customer} not found", "Message Creation Error")
			return None
		
		## Only set customer - customer_name field auto-populates via fetch_from
		message_doc = frappe.get_doc({
			"doctype": "Message",
			"customer": customer,
			"message": message[:200],
			"date": datetime.now().date(),
			"time": datetime.now().time().strftime("%H:%M:%S"),
			"status": status
		})
		
		## Link to source document if provided
		if reference_doctype and reference_name:
			message_doc.reference_doctype = reference_doctype
			message_doc.reference_name = reference_name
		
		message_doc.insert(ignore_permissions=True)
		frappe.db.commit()
		
		return message_doc.name
		
	except Exception as e:
		frappe.log_error(f"Message record failed: {str(e)[:100]}", "Message Creation Error")
		return None


def send_sms(number, message, sender_id=None):
	## Send SMS via EGO SMS gateway
	if not number or not message:
		error = "Invalid number or message"
		frappe.log_error(error, "SMS Validation Error")
		return {"status": "failed", "reason": error}

	try:
		settings = get_sms_settings()
	except Exception as e:
		error = "SMS Settings Config not found"
		frappe.log_error(str(e)[:100], error)
		return {"status": "failed", "reason": error}

	if not settings.username or not settings.api_key:
		error = "SMS Settings incomplete: Username/API Key missing"
		frappe.log_error(error, "SMS Configuration Error")
		return {"status": "failed", "reason": error}

	## Use settings sender_id if none provided
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

	headers = {"Content-Type": "application/json"}

	try:
		response = requests.post(url, json=payload, headers=headers, timeout=20)
		
		## Check HTTP response code
		if response.status_code != 200:
			error_msg = f"SMS API error {response.status_code}"
			frappe.log_error(error_msg, "SMS API Error")
			return {"status": "failed", "reason": error_msg}

		## Parse API response
		try:
			response_json = response.json()
			if response_json.get("Status") == "Failed":
				reason = response_json.get("Message", "Unknown error")
				frappe.log_error(f"SMS Failed: {reason}", "SMS Gateway Error")
				return {"status": "failed", "reason": reason}
		except:
			pass

		return {"status": "sent", "response": response.text[:200]}

	except requests.exceptions.Timeout:
		error = "SMS timeout"
		frappe.log_error(error, "SMS Timeout")
		return {"status": "failed", "reason": error}
	
	except requests.exceptions.ConnectionError as e:
		error = "SMS connection failed"
		frappe.log_error(f"{error}: {str(e)[:50]}", "SMS Connection Error")
		return {"status": "failed", "reason": error}
	
	except Exception as e:
		error = f"SMS failed: {str(e)[:50]}"
		frappe.log_error(error, "SMS Sending Error")
		return {"status": "failed", "reason": error}


def send_sms_to_customer(customer, message, sender_id=None, reference_doctype=None, reference_name=None):
	## Send SMS and create Message record
	
	if not frappe.db.exists("Customer", customer):
		reason = f"Customer {customer} not found"
		frappe.log_error(reason[:100], "SMS Error")
		create_message_record(customer, message, "failed", reference_doctype, reference_name)
		return {"status": "failed", "reason": reason}

	## Get customer doc to extract phone
	customer_doc = frappe.get_doc("Customer", customer)
	number = get_customer_number(customer, customer_doc)

	if not number:
		reason = "No valid phone number"
		frappe.log_error(f"No phone for {customer}", "SMS Error")
		create_message_record(customer, message, "failed", reference_doctype, reference_name)
		return {"status": "failed", "reason": reason}

	## Send SMS
	result = send_sms(number, message, sender_id)
	
	## Create Message record based on result
	status = "sent" if result.get("status") == "sent" else "failed"
	create_message_record(customer, message, status, reference_doctype, reference_name)
	
	return result


def send_payment_entry_sms(doc, method):
	## Send SMS notification on Payment Entry submission
	try:
		## Only process Customer payments
		if doc.party_type != "Customer":
			frappe.logger().info(f"Payment Entry {doc.name} is for {doc.party_type}, skipping SMS")
			return
		
		## Verify SMS Settings configured
		settings = get_sms_settings()
		
		if not settings.username or not settings.api_key:
			frappe.log_error("SMS Settings incomplete", "SMS Configuration Error")
			notify_alert("SMS Settings not configured", "red")
			return

		## Extract customer from Payment Entry
		customer = doc.party
		
		if not customer:
			frappe.log_error(f"Payment Entry {doc.name} has no Customer linked", "Invalid Payment Entry")
			notify_alert("Cannot send SMS: No Customer linked", "red")
			return

		## Get customer display name for message
		customer_doc = frappe.get_doc("Customer", customer)
		customer_name = get_customer_short_name(customer_doc.customer_name or customer)

		## Use reference_no or fallback to Payment Entry name
		reference = doc.reference_no if doc.reference_no else doc.name

		## Build SMS message
		message = (
			f"Dear {customer_name}, payment of UGX {doc.paid_amount:,.0f}/= processed. "
			f"Ref: {reference}. Autozone Professional Limited"
		)
		message = append_inquiry_contacts(message)
		
		## Send SMS
		result = send_sms_to_customer(
			customer,
			message, 
			sender_id=None,
			reference_doctype="Payment Entry",
			reference_name=doc.name
		)

		if result.get("status") == "sent":
			frappe.logger().info(f"SMS sent for Payment Entry {doc.name} to {customer_name}")
			notify_alert("Payment SMS sent successfully", "green")
		else:
			frappe.log_error(
				f"SMS failed for Payment Entry {doc.name}: {result.get('reason')}",
				"SMS Failed"
			)
			notify_alert(f"SMS failed: {result.get('reason')}", "red")
		
	except Exception as e:
		error_msg = f"SMS error for Payment Entry {doc.name}: {str(e)[:100]}"
		frappe.log_error(error_msg, "SMS Error")
		notify_alert("Failed to send payment SMS", "red")


def send_sales_order_sms(doc, method):
	## Send SMS notification on Sales Order submission
	try:
		## Verify SMS Settings configured
		settings = get_sms_settings()
		
		if not settings.username or not settings.api_key:
			frappe.log_error("SMS Settings incomplete", "SMS Configuration Error")
			notify_alert("SMS Settings not configured", "red")
			return

		## Get customer details
		customer = doc.customer
		customer_doc = frappe.get_doc("Customer", customer)
		customer_name = get_customer_short_name(customer_doc.customer_name or customer)
		
		## Build SMS message
		message = f"Dear {customer_name}, order {doc.name} received. Amount: UGX {doc.grand_total:,.0f}/=. Processing soon. Autozone Professional Limited"
		message = append_inquiry_contacts(message)
		
		## Send SMS
		result = send_sms_to_customer(
			customer,
			message, 
			sender_id=None,
			reference_doctype="Sales Order",
			reference_name=doc.name
		)

		if result.get("status") == "sent":
			frappe.logger().info(f"SMS sent for SO {doc.name}")
			notify_alert("SMS sent successfully", "green")
		else:
			frappe.log_error(
				f"SMS failed for SO {doc.name}: {result.get('reason')}",
				"SMS Failed"
			)
			notify_alert(f"SMS failed: {result.get('reason')}", "red")
		
	except Exception as e:
		error_msg = f"SMS error for SO {doc.name}: {str(e)[:100]}"
		frappe.log_error(error_msg, "SMS Error")
		notify_alert("Failed to send SMS notification", "red")
