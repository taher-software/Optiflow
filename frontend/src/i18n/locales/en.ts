const en = {
  translation: {
    tagline: "Keep production flowing.",

    language: { fr: "Français", en: "English" },

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
  },
};

export default en;
