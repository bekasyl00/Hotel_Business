import { computed, ref, watch } from "vue";
import { propertyToday } from "@/entities/booking";
import { money } from "@/shared/lib";
import { request } from "@/shared/api";

export function useWorkspaceBookings({
  session,
  bookings,
  selected,
  current,
  editor,
  confirm,
  busy,
  error,
  notice,
  load,
  t,
}) {
  const paymentDialog = ref(null);
  const canPayStaff = (b) =>
    !session.isAccountant &&
    b.source === "staff" &&
    ["pending", "confirmed"].includes(b.status) &&
    (!b.payment ||
      ["failed", "creating", "pending"].includes(b.payment.status)) &&
    (!b.holdExpiresAt ||
      b.status === "confirmed" ||
      Date.parse(b.holdExpiresAt) > Date.now()) &&
    Date.parse(b.cancellationPolicy?.checkinAt || "") > Date.now();
  async function paymentSaved(result) {
    if (!result.failed) paymentDialog.value = null;
    await load(true);
  }
  const bookingView = ref("calendar"),
    focusedId = ref(null),
    detailError = ref("");
  const focusedBooking = computed(() =>
    bookings.items.find(
      (b) => b.id === focusedId.value && b.resortId === selected.value,
    ),
  );
  function createAt(preset) {
    if (session.isAccountant) return;
    editor.value = { kind: "bookings", preset };
  }
  async function cardAction(action) {
    const booking = focusedBooking.value;
    if (!booking) return;
    if (action === "pay") {
      focusedId.value = null;
      paymentDialog.value = booking;
    } else if (action === "cancel") {
      focusedId.value = null;
      await prepareCancellation(booking);
    } else await changeStay(booking, action);
  }
  async function saveNotes(staffNotes) {
    busy.value = true;
    detailError.value = "";
    const booking = focusedBooking.value;
    try {
      await request("POST", `/bookings/${booking.id}/notes`, {
        version: booking.version,
        staffNotes,
      });
      notice.value = "staff.board.notesSaved";
      await load(true);
    } catch (e) {
      detailError.value = e.message;
    } finally {
      busy.value = false;
    }
  }
  watch(focusedId, () => {
    detailError.value = "";
  });
  watch(selected, () => {
    focusedId.value = null;
  });
  const stayNames = computed(() => ({
    not_arrived: t("staff.awaitingArrival"),
    in_house: t("staff.inHousePaid"),
    checked_out: t("staff.checkedOut"),
  }));
  function canCheckIn(booking) {
    const today = propertyToday(current.value?.timeZone || "Asia/Almaty");
    return (
      booking.status === "confirmed" &&
      booking.payment?.status === "paid" &&
      !booking.checkedInAt &&
      today >= booking.start &&
      today < booking.end
    );
  }
  async function changeStay(booking, action) {
    busy.value = true;
    error.value = "";
    try {
      await request("POST", `/bookings/${booking.id}/${action}`, {
        version: booking.version,
      });
      notice.value =
        action === "check-in" ? "staff.checkInNotice" : "staff.checkOutNotice";
      await load(true);
    } catch (e) {
      if (focusedId.value) detailError.value = e.message;
      else error.value = e.message;
    } finally {
      busy.value = false;
    }
  }
  async function prepareCancellation(item) {
    busy.value = true;
    error.value = "";
    try {
      const preview = await request(
        "GET",
        `/cancellation-preview/${item.id}?asStaff=true`,
      );
      confirm.value = {
        kind: "bookings",
        item,
        title: t("staff.cancelBookingTitle"),
        text: `${t("staff.cancellationPreview", { refund: money(preview.refundAmount), paid: money(preview.paidAmount) })} ${t("staff.refundSchedule")}`,
      };
    } catch (e) {
      error.value = e.message;
    } finally {
      busy.value = false;
    }
  }
  return {
    paymentDialog,
    bookingView,
    focusedId,
    focusedBooking,
    detailError,
    stayNames,
    canPayStaff,
    paymentSaved,
    createAt,
    cardAction,
    saveNotes,
    canCheckIn,
    changeStay,
    prepareCancellation,
  };
}
