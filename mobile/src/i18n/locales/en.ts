const en = {
  translation: {
    prospect: {
      badge: "The operations platform for modern plants",
      headline: "Keep production flowing.",
      subhead:
        "Operio connects your teams, machines and data so your plant runs smoother — everything you need to keep production moving, in one place.",
      values: {
        visibility: "Real-time visibility across your plant",
        response: "Faster, coordinated response on the floor",
        improve: "Data-driven continuous improvement",
      },
      connecting: "Connecting…",
      retry: "Tap to retry",
    },
    securityCode: {
      title: "Enter your security code",
      subtitle:
        "Type the 4-character security code assigned to you to pair this device.",
      label: "Security code",
      save: "Save",
      saving: "Pairing…",
      invalid: "Enter your 4-character code.",
      invalidChars:
        "Check your code: it only uses digits and letters, without I, L, O or U.",
    },
    home: {
      greeting: "Welcome",
      overview: "Downtime at a glance",
      declare: "Declare a downtime",
      online: {
        label: "My availability",
        on: "Online",
        off: "Offline",
        escalationNote:
          "You still receive supervisor escalations while offline.",
        error: "Could not update your availability. Please try again.",
      },
    },
    downtime: {
      avgTime: "Avg",
      status: {
        pending: "Pending",
        ongoing: "Ongoing",
        resolved: "Resolved",
        closed: "Closed",
      },
      process: {
        maintenance: "Maintenance",
        quality: "Quality",
        production: "Production",
        logistic: "Logistics",
      },
      scope: {
        plant: "Entire plant",
        uap: "Zone area (UAP)",
        production_line: "Production line",
        work_station: "Work station",
      },
      type: {
        break_down: "Breakdown",
        quality_issue: "Quality issue",
        Absenteeism: "Absenteeism",
        Work_in_Process_WIP_Shortage: "WIP shortage",
        Material_Component_Shortage: "Material / component shortage",
        Setup_Changeover: "Setup / changeover",
        others: "Other / unknown cause",
      },
      list: {
        empty: "No downtime here.",
        inStatus: "for {{time}}",
      },
      detail: {
        scope: "Scope",
        uap: "Zone area",
        line: "Production line",
        station: "Work station",
        createdAt: "Created at",
        createdBy: "Opened by",
        ackAt: "Acknowledged at",
        ackBy: "Acknowledged by",
        resolvedAt: "Resolved at",
        resolvedBy: "Resolved by",
        closedAt: "Closed at",
        closedBy: "Closed by",
        acknowledge: "Acknowledge",
        resolve: "Mark as resolved",
        reject: "Reject resolution",
        rejectTitle: "Reject this resolution?",
        rejectConfirm:
          "The ticket goes back to the responders as still unresolved.",
        rejectedAt: "Resolution rejected at",
        rejectedBy: "Rejected by",
        rejectionCount: "Times rejected",
        close: "Mark as closed",
        delete: "Delete",
        cancel: "Cancel",
        deleteTitle: "Delete downtime",
        deleteConfirm: "Delete this downtime? This cannot be undone.",
        notFound: "This downtime is no longer available.",
        back: "Back",
      },
      declare: {
        title: "Declare a downtime",
        scope: "What is affected?",
        uap: "Zone area",
        line: "Production line",
        station: "Work station",
        type: "Cause",
        department: "Department",
        independent: "Independent",
        noLines: "No production line for this selection.",
        noStations: "No work station for this selection.",
        save: "Report downtime",
        success: "Downtime reported.",
        conflict:
          "A downtime is already open on this resource. Update the existing ticket instead of declaring a new one.",
      },
    },
    errors: {
      codeNotFound: "No user is available for this code.",
      deviceLocked:
        "This device has been temporarily locked out after too many failed pairing attempts. Please wait about an hour before trying again.",
      generic: "Something went wrong. Please try again.",
      network: "Cannot reach the server. Check your connection.",
    },
  },
};

export default en;
