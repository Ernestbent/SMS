import frappe
from frappe.utils import strip_html_tags

from sms.sms.custom_scripts.sms_message import create_message_record, send_sms
from sms.sms.utils.utils import normalize_ug_number


CREDIT_CONTROLLER_ROLE = "Credit Controller"


def get_credit_controller_users():
    """Return enabled users that have the Credit Controller role."""
    users = frappe.get_all(
        "Has Role",
        filters={"role": CREDIT_CONTROLLER_ROLE, "parenttype": "User"},
        fields=["parent"],
    )
    seen = set()
    unique_users = []

    for row in users:
        if row.parent in seen:
            continue
        seen.add(row.parent)
        unique_users.append(row)

    return unique_users


def get_user_mobile_no(user_id):
    """Read the SMS number stored on the User record."""
    if not user_id or not frappe.db.exists("User", user_id):
        return None

    if not frappe.db.get_value("User", user_id, "enabled"):
        return None

    phone = frappe.db.get_value("User", user_id, "phone")
    if not phone:
        phone = frappe.db.get_value("User", user_id, "mobile_no")

    return normalize_ug_number(phone)


def user_has_role(user_id, role_name):
    """Check whether a user has a specific role."""
    if not user_id:
        return False

    return bool(
        frappe.db.exists(
            "Has Role",
            {
                "parenttype": "User",
                "parent": user_id,
                "role": role_name,
            },
        )
    )


def resolve_customer_from_reference(comment_doc):
    """
    Resolve the customer linked to the commented document.

    We support:
    - comments directly on Customer
    - documents that expose a `customer` field
    - documents that expose a `party` field with `party_type = Customer`
    """
    reference_doctype = comment_doc.reference_doctype
    reference_name = comment_doc.reference_name

    if not reference_doctype or not reference_name:
        return None

    if reference_doctype == "Customer":
        return reference_name

    if not frappe.db.exists(reference_doctype, reference_name):
        return None

    ref_doc = frappe.get_doc(reference_doctype, reference_name)

    if getattr(ref_doc, "customer", None):
        return ref_doc.customer

    if getattr(ref_doc, "party_type", None) == "Customer" and getattr(ref_doc, "party", None):
        return ref_doc.party

    return None


def build_comment_message(comment_doc, customer_name):
    """Build the SMS text that will be sent to the Credit Controller role."""
    comment_text = strip_html_tags(comment_doc.content or "").strip()
    comment_text = " ".join(comment_text.split())
    reference = f"{comment_doc.reference_doctype} {comment_doc.reference_name}"
    author = comment_doc.comment_by or comment_doc.comment_email or comment_doc.owner or "Unknown user"

    return (
        f"{author} commented on {reference} for customer {customer_name}: "
        f"{comment_text}"
    )


def get_reference_owner(comment_doc):
    """Return the owner of the referenced document."""
    if not comment_doc.reference_doctype or not comment_doc.reference_name:
        return None

    if not frappe.db.exists(comment_doc.reference_doctype, comment_doc.reference_name):
        return None

    return frappe.db.get_value(
        comment_doc.reference_doctype,
        comment_doc.reference_name,
        "owner",
    )


def get_comment_recipients(comment_doc):
    """Build the recipient list for a comment event."""
    commenter = comment_doc.owner

    if user_has_role(commenter, CREDIT_CONTROLLER_ROLE):
        creator = get_reference_owner(comment_doc)
        return [creator] if creator and creator != commenter else []

    recipients = []
    for row in get_credit_controller_users():
        if row.parent != commenter:
            recipients.append(row.parent)

    # Keep unique recipients while preserving order.
    seen = set()
    unique_recipients = []
    for user_id in recipients:
        if user_id in seen:
            continue
        seen.add(user_id)
        unique_recipients.append(user_id)

    return unique_recipients


def send_and_log_sms(customer, mobile_no, message, reference_doctype, reference_name, recipient_user=None):
    """Send SMS and record the outgoing message in the Message doctype."""
    result = send_sms(mobile_no, message)
    status = "sent" if result.get("status") == "sent" else "failed"

    create_message_record(
        customer,
        message,
        status=status,
        reference_doctype=reference_doctype,
        reference_name=reference_name,
    )

    if status != "sent" and recipient_user:
        frappe.log_error(
            f"Failed to send comment SMS to {recipient_user}: {result.get('reason')}",
            "Comment SMS Error",
        )

    return result


def send_comment_sms_to_credit_controller(doc, method=None):
    """
    Send an SMS for every new comment to all Credit Controller users.

    The message includes the exact comment text and the resolved customer.
    """
    try:
        if getattr(doc, "comment_type", None) and doc.comment_type != "Comment":
            return

        customer = resolve_customer_from_reference(doc)
        if not customer:
            frappe.logger().info(
                f"Skipping comment SMS for {doc.name}: no customer could be resolved"
            )
            return

        customer_label = frappe.db.get_value("Customer", customer, "customer_name") or customer
        message = build_comment_message(doc, customer_label)

        recipients = get_comment_recipients(doc)
        if not recipients:
            frappe.log_error(
                "No recipients found for comment SMS",
                "Comment SMS Recipient Error",
            )
            return

        sent_count = 0
        skipped_count = 0

        for recipient in recipients:
            mobile_no = get_user_mobile_no(recipient)
            if not mobile_no:
                skipped_count += 1
                continue

            result = send_and_log_sms(
                customer,
                mobile_no,
                message,
                doc.reference_doctype,
                doc.reference_name,
                recipient_user=recipient,
            )
            if result.get("status") == "sent":
                sent_count += 1
            else:
                skipped_count += 1

        frappe.logger().info(
            f"Comment SMS processed for {doc.name}: sent={sent_count}, skipped={skipped_count}"
        )

    except Exception as e:
        frappe.log_error(
            f"Comment SMS failed for {getattr(doc, 'name', 'unknown')}: {str(e)[:200]}",
            "Comment SMS Error",
        )
