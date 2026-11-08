export function staffNavigation(role) {
  const finance = ["accounting", "₸", "common.accounting.title"];
  const analytics = ["analytics", "↗", "staff.analytics"];
  const planner = ["bookings", "▤", "staff.board.title"];
  if (role === "accountant") return [finance, analytics, planner];
  return [
    ...(role === "admin" ? [finance] : []),
    ["overview", "◫", "staff.overview"],
    analytics,
    ["resorts", "⌖", "staff.resorts"],
    ["rooms", "▦", "staff.rooms"],
    planner,
    ["reviews", "☆", "staff.reviews"],
    ...(role === "admin"
      ? [
          ["history", "◷", "staff.history"],
          ["clients", "♧", "staff.directory.clients"],
          ["accounts", "♙", "staff.managers"],
        ]
      : []),
  ];
}
