const en = {
  translation: {
    tagline: "Keep production flowing.",

    language: { fr: "Français", en: "English" },

    common: { showPassword: "Show password", hidePassword: "Hide password" },

    prospect: {
      badge: "Downtime management for modern plants",
      hero: {
        headline: "Stop losing hours to machine downtime.",
        subhead:
          "OptiFlow is the multi-tenant platform that detects every stoppage, drives it to resolution, and helps your plant eliminate downtime for good.",
        primaryCta: "Request a demo",
        secondaryCta: "See how it works",
      },
      features: {
        automate: {
          title: "Automate downtime management",
          description:
            "The instant a workstation stops, OptiFlow opens a ticket, notifies the right responder, and follows it through acknowledge, repair, and validated recovery — no manual chasing.",
        },
        empower: {
          title: "Empower your staff",
          description:
            "Give operators and technicians one clear workflow on any device: see the issue, acknowledge it, and keep the ticket updated from the floor to the finish.",
        },
        transparent: {
          title: "Transparent planning",
          description:
            "Every stoppage, timestamp, and action is visible in real time. Plans are built on what is actually happening on the line — not on guesswork.",
        },
        rootcause: {
          title: "Identify & eradicate root causes",
          description:
            "Turn downtime history into root-cause insight, then eliminate recurring failures so the same machine never steals the same hour twice.",
        },
      },
      closing: {
        title: "Turn downtime into uptime.",
        subtitle:
          "See how OptiFlow keeps your production flowing — from the first stoppage alert to a root cause you never have to face again.",
      },
      footer: "© {{year}} OptiFlow. Keep production flowing.",
    },

    login: {
      title: "Sign in",
      subtitle: "Access your production workspace.",
      emailLabel: "Email",
      passwordLabel: "Password",
      submit: "Sign in",
      submitting: "Signing in…",
      noAccount: "No account yet?",
      createAccount: "Create an account",
      errors: {
        required: "Email and password are required.",
        invalidCredentials: "Invalid username or password.",
        notConfirmed: "Please confirm your account before signing in.",
        failed: "Sign-in failed.",
      },
    },

    register: {
      title: "Create an account",
      stepLabel: "Step {{step}} of 2 — {{part}}",
      partCompany: "your company",
      partOwner: "you",
      fields: {
        companyName: "Company name",
        address: "Address",
        postalCode: "Postal code",
        city: "City",
        country: "Country",
        phone: "Phone",
        taxId: "Tax identification number",
        firstName: "First name",
        lastName: "Last name",
        email: "Email",
        avatar: "Avatar (URL, optional)",
      },
      next: "Next",
      back: "Back",
      submit: "Create my account",
      submitting: "Creating…",
      alreadyAccount: "Already have an account?",
      signIn: "Sign in",
      success: {
        title: "Account created 🎉",
        message:
          "A confirmation email has been sent to {{email}}. Click the link inside to activate your account.",
        resendPrompt: "Didn't get it? Resend the email",
        resent: "Email resent, check your inbox.",
      },
      errors: {
        createFailed: "Account creation failed.",
        sendFailed: "Sending failed.",
      },
    },

    confirm: {
      confirming: "Confirming…",
      success: {
        title: "Account confirmed ✅",
        message:
          "Your credentials have been emailed to you. You can now sign in.",
        signIn: "Sign in",
      },
      error: {
        title: "Confirmation failed",
        invalidLink: "Invalid confirmation link.",
        default: "Confirmation failed.",
      },
      resend: {
        prompt:
          "Link expired or invalid? Resend yourself a confirmation email:",
        submit: "Resend the confirmation email",
        submitting: "Sending…",
        sent: "A new confirmation email has just been sent.",
        failed: "Sending failed.",
      },
      backToLogin: "Back to sign in",
    },

    dashboard: {
      greeting: "Welcome",
      subtitle:
        "Your production dashboard is coming soon — downtime tickets, responders, and plant KPIs.",
      signOut: "Sign out",
    },

    nav: {
      dashboard: "Dashboard",
      users: "Users",
      uaps: "Production areas",
      lines: "Production lines",
      stations: "Work stations",
    },

    lines: {
      title: "Production lines",
      add: "Add a production line",
      empty: "No production lines yet.",
      loading: "Loading…",
      edit: "Edit",
      table: {
        name: "Name",
        zoneArea: "Zone area",
        description: "Description",
        actions: "Actions",
      },
      form: {
        createTitle: "New production line",
        editTitle: "Edit production line",
        name: "Name",
        namePlaceholder: "e.g. Line 1",
        description: "Description",
        descriptionPlaceholder: "What this line produces…",
        zoneArea: "Zone area",
        zoneAreaPlaceholder: "Select a production area…",
        save: "Save",
        creating: "Creating…",
        saving: "Saving…",
        cancel: "Cancel",
        delete: "Delete",
        deleting: "Deleting…",
        confirmDelete: "Delete this production line? This cannot be undone.",
        loadError: "Could not load the production line.",
        saveError: "Could not save the production line.",
        deleteError: "Could not delete the production line.",
      },
    },

    stations: {
      title: "Work stations",
      add: "Add a workstation",
      empty: "No workstations yet.",
      loading: "Loading…",
      edit: "Edit",
      independent: "Independent",
      types: {
        standard: "Standard",
        bottleneck: "Bottleneck",
        critical: "Critical",
      },
      table: {
        name: "Name",
        type: "Type",
        line: "Production line",
        actions: "Actions",
      },
      form: {
        createTitle: "New workstation",
        editTitle: "Edit workstation",
        name: "Name",
        namePlaceholder: "e.g. Station A3",
        description: "Description",
        descriptionPlaceholder: "What this station does…",
        line: "Production line",
        independent: "Independent (no line)",
        type: "Type",
        save: "Save",
        creating: "Creating…",
        saving: "Saving…",
        cancel: "Cancel",
        delete: "Delete",
        deleting: "Deleting…",
        confirmDelete: "Delete this workstation? This cannot be undone.",
        loadError: "Could not load the workstation.",
        saveError: "Could not save the workstation.",
        deleteError: "Could not delete the workstation.",
      },
    },

    uaps: {
      title: "Production areas",
      add: "Add a production area",
      empty: "No production areas yet.",
      loading: "Loading…",
      edit: "Edit",
      memberCount: "{{count}} resource",
      memberCount_other: "{{count}} resources",
      form: {
        createTitle: "New production area",
        editTitle: "Edit production area",
        name: "Name",
        namePlaceholder: "e.g. Assembly line A",
        description: "Description",
        descriptionPlaceholder: "What this area covers…",
        resources: "Assigned resources",
        noMembers: "No users with this role yet.",
        save: "Save",
        creating: "Creating…",
        saving: "Saving…",
        cancel: "Cancel",
        delete: "Delete",
        deleting: "Deleting…",
        confirmDelete: "Delete this production area? This cannot be undone.",
        loadError: "Could not load the production area.",
        saveError: "Could not save the production area.",
        deleteError: "Could not delete the production area.",
      },
    },

    users: {
      title: "Users",
      add: "Add a user",
      empty: "No users yet.",
      loading: "Loading…",
      edit: "Edit",
      table: {
        name: "Name",
        role: "Role",
        email: "Email",
        securityCode: "Security code",
        actions: "Actions",
      },
      form: {
        createTitle: "New user",
        editTitle: "Edit user",
        firstName: "First name",
        lastName: "Last name",
        role: "Role",
        roleLocked: "cannot be changed",
        email: "Email",
        optional: "optional",
        password: "Password",
        passwordEdit: "New password",
        passwordEditHint: "Leave blank to keep unchanged",
        save: "Save",
        creating: "Creating…",
        saving: "Saving…",
        cancel: "Cancel",
        loadError: "Could not load the user.",
        saveError: "Could not save the user.",
      },
      roles: {
        owner: {
          name: "Owner",
          description:
            "Owns the organization. Has unrestricted access to all features, billing, subscriptions, organizational settings, sites, users, and permissions.",
        },
        admin: {
          name: "Admin",
          description:
            "Manages the organization's configuration, users, permissions, sites, production structures, and system settings. Has full operational access but does not own the organization.",
        },
        manager: {
          name: "Manager",
          description:
            "Department or plant manager responsible for overall operational performance. Has visibility across multiple workshops, production lines, and teams, with authority to monitor KPIs, allocate resources, and make strategic decisions.",
        },
        production_supervisor: {
          name: "Production Supervisor",
          description:
            "Supervises production activities across one or more workshops. Coordinates production agents, monitors performance, resolves escalated issues, and ensures production targets are achieved.",
        },
        production_agent: {
          name: "Production Agent",
          description:
            "Field production leader responsible for daily operations within a production area. May represent a Team Leader, Shift Leader, UAP Leader, Cell Leader, or any operational leader directly managing production activities and reporting incidents.",
        },
        quality_supervisor: {
          name: "Quality Supervisor",
          description:
            "Supervises quality activities, coordinates quality agents, validates inspections, monitors quality KPIs, and ensures compliance with quality standards.",
        },
        quality_agent: {
          name: "Quality Agent",
          description:
            "Field quality leader responsible for inspections, audits, non-conformity management, and quality control activities within an assigned area.",
        },
        maintenance_supervisor: {
          name: "Maintenance Supervisor",
          description:
            "Supervises maintenance operations, prioritizes interventions, coordinates maintenance agents, and ensures equipment reliability and maintenance planning.",
        },
        maintenance_agent: {
          name: "Maintenance Agent",
          description:
            "Field maintenance leader responsible for coordinating maintenance work in a workshop, production line, or technical area. May represent a Maintenance Team Leader or Area Maintenance Coordinator.",
        },
        logistic_supervisor: {
          name: "Logistic Supervisor",
          description:
            "Supervises logistics operations, warehouse activities, material flow, and coordinates logistics agents.",
        },
        logistic_agent: {
          name: "Logistic Agent",
          description:
            "Field logistics leader responsible for warehouse operations, material supply, shipping, receiving, or inventory activities within an assigned operational area.",
        },
      },
    },
  },
};

export default en;
