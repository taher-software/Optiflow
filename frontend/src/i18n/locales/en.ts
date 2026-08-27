const en = {
  translation: {
    tagline: "Keep production flowing.",

    language: { fr: "Français", en: "English" },

    legal: {
      taxId: "Tax identification number:",
      lastUpdated: "Last updated:",
      backToHome: "Back to the home page",

      privacy: {
        title: "Privacy Policy",
        updated: "27 August 2026",
        sections: {
          controller: {
            heading: "Who is responsible for your data",
            body: "OptiFlow is published and operated by {{tradeName}} {{legalForm}}, registered office {{registeredOffice}}, tax identification number {{taxId}}.\n\n{{tradeName}} {{legalForm}} is the data controller for the account, contact and billing data of its customers. For the operational data a plant records in OptiFlow, it acts on that plant's instructions as a data processor.\n\nFor any question about this policy, or to exercise your rights, contact us at {{contactEmail}} or {{contactPhone}}.",
          },
          data: {
            heading: "What we collect",
            body: "Account data: first and last name, professional email address, phone number where you provide one, your role in the plant, and the organization you belong to.\n\nOperational data: the downtime tickets you open, acknowledge or resolve, the workstations, production lines and production areas you configure, and the timestamps of each step of the downtime lifecycle.\n\nTechnical data: connection logs, IP address, browser and device type, and the pages of the application you visit.\n\nWe do not collect sensitive personal data, and we never use your data for advertising.",
          },
          purposes: {
            heading: "Why we use it",
            body: "To provide the service: create your account, authenticate you, and give you access to your organization's data only.\n\nTo run the downtime workflow: notify the right responders, track acknowledgement and resolution, and compute your plant's KPIs.\n\nTo keep the service secure and available: detect abuse, diagnose incidents, and maintain audit logs.\n\nTo support and bill you: answer your requests and manage the subscription.",
          },
          basis: {
            heading: "Legal basis",
            body: "We process your data to perform the contract that binds us to your organization, to comply with our legal and accounting obligations, and on the basis of our legitimate interest in keeping the service secure. Where consent is required, we ask for it and you may withdraw it at any time.",
          },
          retention: {
            heading: "How long we keep it",
            body: "Account data is kept for as long as your organization's subscription is active, then for 12 months after it ends.\n\nOperational data (tickets, KPIs) is kept for the duration of the subscription and can be exported or deleted at your organization's request.\n\nTechnical logs are kept for 12 months.\n\nAccounting records are kept for the period required by the applicable tax law.",
          },
          sharing: {
            heading: "Who we share it with",
            body: "We do not sell your data and we do not share it with third parties for their own purposes.\n\nWe rely on the following processors, each bound by a contract and acting only on our instructions:\n\n· Google Cloud (Firestore, Pub/Sub, Cloud Tasks, Cloud Run) — hosting and data storage, in the europe-west1 region.\n· Resend — sending transactional email such as account confirmation and downtime notifications.\n\nWe may also disclose data where required by law or by a competent authority.",
          },
          security: {
            heading: "Security",
            body: "Data is encrypted in transit (HTTPS) and at rest by our hosting provider. Access is restricted to the members of your own organization: every request is scoped to your tenant, and no data crosses from one plant to another.\n\nAccess by our staff is limited to what is strictly necessary for operating and supporting the service.",
          },
          rights: {
            heading: "Your rights",
            body: "You may request access to your data, its correction, its deletion, a portable copy, or the restriction of its processing. You may also object to a given processing operation.\n\nSend your request to {{contactEmail}}. We reply within one month. If you belong to a customer organization, we may need to forward your request to that organization, which decides on the operational data it controls.",
          },
          cookies: {
            heading: "Cookies and local storage",
            body: "OptiFlow does not use advertising or third-party tracking cookies.\n\nThe web application stores two items in your browser's local storage: your session token, so you stay signed in, and your language preference. Clearing your browser data removes both and signs you out.",
          },
          children: {
            heading: "Children",
            body: "OptiFlow is a professional tool intended for plant staff. It is not directed at, and must not be used by, persons under 16.",
          },
          changes: {
            heading: "Changes to this policy",
            body: "We may update this policy to reflect changes to the service or to the law. The date at the top of this page always shows the current version, and we notify customer organizations of any substantial change.",
          },
        },
      },

      terms: {
        title: "Terms of Sale",
        updated: "27 August 2026",
        sections: {
          purpose: {
            heading: "1. Purpose",
            body: 'These terms of sale govern the subscription to and use of the OptiFlow service, published by {{tradeName}} {{legalForm}}, registered office {{registeredOffice}}, tax identification number {{taxId}} (the "Publisher").\n\nThey are accepted by the customer when the subscription is signed and prevail over any of the customer\'s own purchasing terms.',
          },
          service: {
            heading: "2. The service",
            body: "OptiFlow is a software-as-a-service platform for managing machine downtime in manufacturing plants. It covers detecting a stoppage, notifying the responders, acknowledging and tracking the ticket, validating the return to production, and computing the resulting plant KPIs.\n\nThe service is accessed over the internet through a web application and a mobile application. No installation on the customer's servers is required.",
          },
          account: {
            heading: "3. Accounts and access",
            body: "Each customer organization has its own isolated space. The customer appoints an administrator who creates and manages user accounts and their roles.\n\nCredentials are personal and confidential. The customer is responsible for their use and must inform the Publisher without delay of any suspected compromise.",
          },
          subscription: {
            heading: "4. Subscription",
            body: "The subscription is taken out for the scope stated in the quote or order form accepted by the customer: number of users, sites and options.\n\nAny extension of that scope during the term is billed on a pro-rata basis under the same conditions.",
          },
          pricing: {
            heading: "5. Pricing",
            body: "Prices are those set out in the quote or order form accepted by the customer. They are stated exclusive of tax; applicable taxes are added at the rate in force on the invoice date.\n\nPrices may be revised at each renewal. The Publisher gives at least 60 days' notice before the renewal date; the customer may then terminate under section 7.",
          },
          payment: {
            heading: "6. Payment",
            body: "Invoices are payable within 30 days of their issue date, by bank transfer, unless the order form provides otherwise.\n\nAny sum unpaid on its due date bears late-payment interest at the legal rate, without the need for a formal notice. After a reminder that remains unanswered for 15 days, the Publisher may suspend access until payment is received.",
          },
          duration: {
            heading: "7. Term and termination",
            body: "The subscription runs for the term stated in the order form and renews for equal periods unless either party terminates it in writing at least 30 days before the end of the current period.\n\nEither party may terminate for a material breach that remains uncured 30 days after a written notice.\n\nOn termination, the customer may export its data for 30 days. After that period, the data is deleted under the conditions of the privacy policy.",
          },
          obligations: {
            heading: "8. Customer obligations",
            body: "The customer undertakes to use the service in accordance with these terms and with the applicable law, to provide accurate information, to keep its user accounts up to date, and not to attempt to circumvent the technical measures protecting the service or to access another organization's data.\n\nThe customer is responsible for the content it records in the service and for informing its own staff of the processing carried out.",
          },
          availability: {
            heading: "9. Availability and support",
            body: "The Publisher undertakes to use its best efforts to keep the service available around the clock, excluding scheduled maintenance, which is announced in advance whenever possible, and excluding failures of third-party providers or of the customer's own connection.\n\nSupport is available on business days at {{contactEmail}} and {{contactPhone}}. Any specific availability or response commitment is the one stated in the order form.",
          },
          liability: {
            heading: "10. Liability",
            body: "The Publisher is bound by an obligation of means. Its liability is limited to direct damage and, in the aggregate, to the amounts paid by the customer over the twelve months preceding the event giving rise to the claim.\n\nThe Publisher is not liable for indirect damage, in particular loss of production, loss of turnover or loss of data resulting from a cause outside its control.\n\nOptiFlow is a management and traceability tool. It does not replace the customer's safety procedures or its regulatory obligations regarding its equipment.",
          },
          intellectualProperty: {
            heading: "11. Intellectual property",
            body: "The service, its software, its interfaces and its documentation remain the exclusive property of the Publisher. The subscription grants a non-exclusive, non-transferable right to use them for the term of the subscription and for the customer's internal needs only.\n\nThe data recorded by the customer remains the customer's property.",
          },
          dataProtection: {
            heading: "12. Personal data",
            body: "Each party complies with the applicable personal-data legislation. The processing carried out by the Publisher is described in the privacy policy, which forms an integral part of these terms.",
          },
          law: {
            heading: "13. Governing law and disputes",
            body: "These terms are governed by Tunisian law.\n\nThe parties will seek an amicable settlement of any dispute. Failing agreement within 30 days, the dispute falls under the exclusive jurisdiction of the competent courts of Sousse, Tunisia.",
          },
        },
      },
    },

    common: {
      showPassword: "Show password",
      hidePassword: "Hide password",
      errors: {
        title: "The data could not be loaded.",
        unreachable: "Cannot reach the server.",
        unreachableHint:
          "The server is unreachable, so no data could be retrieved. Check your connection, then try again.",
        retry: "Try again",
      },
    },

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
      eyebrow: "Plant",
      title: "Plant dashboard",
      subtitle:
        "Downtime KPIs — click a shift, a location, a process or a type to break it down.",
      signOut: "Sign out",
      loading: "Loading…",
      empty: "No data for this period.",
      exploreStats: "Explore stats",
      compareEpisodes: "Compare two episodes",
      shiftN: "Shift {{n}}",
      rowMeta: "{{count}} downtimes · MTTR {{mttr}}",
      paretoCumul: "cumul. {{pct}} %",
      kpi: {
        downtime: "Downtime",
        count: "Number of downtimes",
        mttr: "MTTR",
        mtbf: "MTBF",
        downtimeHint:
          "Totalled per workstation: downtime declared on a group (line, UAP, plant) counts once for every workstation it halts.",
        mttrHint: "mean time to repair",
        mtbfHint: "mean time between failures",
      },
      period: {
        today: "Today",
        "7d": "7 days",
        "30d": "30 days",
        custom: "Range…",
        from: "From",
        to: "To",
      },
      cards: {
        byShift: "Downtime by shift",
        byUap: "Downtime by production area",
        byLine: "Downtime by production line",
        byStation: "Downtime by work station",
        pareto: "Downtime causes by process (Pareto)",
        repair: "Repair time by process",
        byType: "Downtime by type",
        clickHint: "click to explore",
        paretoHint: "click for the per-responder detail",
        repairHint: "cumulated MTTR",
      },
      dimension: {
        shift: "Shift",
        uap: "Production area",
        line: "Production line",
        station: "Work station",
        process: "Process",
        type: "Downtime type",
      },
      process: {
        maintenance: "Maintenance",
        production: "Production",
        quality: "Quality",
        logistic: "Logistics",
      },
      types: {
        break_down: "Machine breakdown",
        quality_issue: "Quality issue",
        absenteeism: "Absenteeism",
        wip_shortage: "WIP shortage",
        material_shortage: "Material shortage",
        setup_changeover: "Setup / Changeover",
        others: "Other",
      },
      filters: {
        process: "Process",
        shift: "Shift",
        allProcesses: "All processes",
        allShifts: "All shifts",
      },
      drill: {
        root: "Plant",
        close: "Close",
        loading: "Loading details…",
        associatedProcess: "Usual process:",
        childrenTitle: "Downtime by location",
        locationsHint: "click a location to go down the hierarchy",
        linesHint: "click a line to go down to its stations",
        noLinesHint: "this area has no lines — stations directly",
        stationsHint: "stations of this line",
        mttrByAgent: "MTTR by responder",
        countByAgent: "Number of downtimes by responder",
        downtimeByShift: "Downtime by shift",
        downtimeByType: "Downtime by type",
      },
    },

    stats: {
      eyebrow: "Stats · Explorer",
      title: "Explore the data",
      subtitle:
        "Daily tracking or two-episode comparison — metric, scope, process, shift and period.",
      mode: { follow: "Daily tracking", compare: "⇄ Compare two episodes" },
      metric: {
        duration: "Downtime",
        count: "Number of downtimes",
        mttr: "MTTR",
      },
      metricTitle: {
        duration: "Daily downtime",
        count: "Downtimes per day",
        mttr: "Daily MTTR",
      },
      filters: { scope: "Scope", wholePlant: "Whole plant" },
      byShift: "Split by shift",
      byProcess: "Split by process",
      compare: {
        ep1: "Episode 1",
        ep2: "Episode 2",
        total1: "Episode 1 total",
        total2: "Episode 2 total",
        average1: "Episode 1 average MTTR",
        average2: "Episode 2 average MTTR",
        gap: "Gap",
        gapBasis: "{{latest}} (most recent) vs {{reference}}",
        gapUndefined: "{{reference}} is zero: gap cannot be computed",
        title: "Episode 1 vs Episode 2",
        axisHint:
          "X axis: day of the episode (D1 → Dn) — both periods aligned by day index.",
      },
    },

    nav: {
      dashboard: "Dashboard",
      stats: "Stats",
      users: "Users",
      uaps: "Production areas",
      lines: "Production lines",
      stations: "Work stations",
      settings: "Settings",
    },

    settings: {
      title: "Plant settings",
      subtitle:
        "Configure your plant's shift schedule and downtime escalation delay.",
      loading: "Loading…",
      shiftNumber: {
        label: "Number of shifts",
        help: "How many shifts the plant runs per day. For example, a plant running 24/7 with three 8-hour shifts has 3.",
      },
      shift: {
        title: "Shift {{number}}",
        window: "Working window",
        start: "Start time",
        end: "End time",
        break: "Break (optional)",
        breakStart: "Break start",
        breakEnd: "Break end",
        breakHelp:
          "The break is subtracted from the shift window to get planned time, which drives the MTBF (mean time between downtimes). Leave both fields empty if the shift has no break.",
        errors: {
          missingWindow: "Enter the shift start time and end time.",
          zeroLengthWindow: "The shift start and end times must differ.",
          breakIncomplete:
            "Enter both the break start and end, or leave both fields empty.",
          breakOutsideWindow:
            "The break must fall inside the shift working window.",
          breakLength:
            "The break must be longer than zero and shorter than the shift window.",
        },
      },
      escalate: {
        label: "Escalation delay (seconds)",
        help: "How long a downtime may stay unresolved before it is escalated to managers. Default is 1800 seconds (30 minutes).",
        approx: "(≈ {{minutes}} min)",
      },
      save: "Save settings",
      saving: "Saving…",
      saved: "Settings saved.",
      saveError: "Could not save the settings.",
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
