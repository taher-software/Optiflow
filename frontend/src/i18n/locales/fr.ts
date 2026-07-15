const fr = {
  translation: {
    tagline: "Gardez votre production en flux.",

    language: { fr: "Français", en: "English" },

    prospect: {
      badge: "La gestion des arrêts pour les usines modernes",
      hero: {
        headline: "Ne perdez plus d'heures à cause des arrêts machine.",
        subhead:
          "OptiFlow est la plateforme multi-tenant qui détecte chaque arrêt, le pilote jusqu'à sa résolution et aide votre usine à éliminer durablement les temps d'arrêt.",
        primaryCta: "Demander une démo",
        secondaryCta: "Découvrir le fonctionnement",
      },
      features: {
        automate: {
          title: "Automatiser la gestion des arrêts",
          description:
            "Dès qu'un poste s'arrête, OptiFlow ouvre un ticket, notifie le bon intervenant et le suit jusqu'à la prise en charge, la réparation et la reprise validée — sans relance manuelle.",
        },
        empower: {
          title: "Donner du pouvoir à vos équipes",
          description:
            "Offrez aux opérateurs et techniciens un flux de travail clair sur tout appareil : voir l'incident, le prendre en charge et mettre à jour le ticket, de l'atelier jusqu'à la clôture.",
        },
        transparent: {
          title: "Une planification transparente",
          description:
            "Chaque arrêt, horodatage et action est visible en temps réel. Les plans reposent sur ce qui se passe réellement sur la ligne — pas sur des suppositions.",
        },
        rootcause: {
          title: "Identifier et éradiquer les causes racines",
          description:
            "Transformez l'historique des arrêts en analyse des causes racines, puis éliminez les pannes récurrentes pour qu'une même machine ne vous coûte jamais deux fois la même heure.",
        },
      },
      closing: {
        title: "Transformez les arrêts en temps de production.",
        subtitle:
          "Découvrez comment OptiFlow maintient votre production en flux — de la première alerte d'arrêt à une cause racine que vous n'aurez plus jamais à affronter.",
      },
      footer: "© {{year}} OptiFlow. Gardez votre production en flux.",
    },

    login: {
      title: "Se connecter",
      subtitle: "Accédez à votre espace de production.",
      emailLabel: "Email",
      passwordLabel: "Mot de passe",
      submit: "Se connecter",
      submitting: "Connexion…",
      noAccount: "Pas encore de compte ?",
      createAccount: "Créer un compte",
      errors: {
        required: "Email et mot de passe requis.",
        failed: "Échec de la connexion.",
      },
    },

    register: {
      title: "Créer un compte",
      stepLabel: "Étape {{step}} sur 2 — {{part}}",
      partCompany: "votre entreprise",
      partOwner: "vous",
      fields: {
        companyName: "Nom de l'entreprise",
        address: "Adresse",
        postalCode: "Code postal",
        city: "Ville",
        country: "Pays",
        phone: "Téléphone",
        taxId: "Numéro d'identification fiscale",
        firstName: "Prénom",
        lastName: "Nom",
        email: "Email",
        avatar: "Avatar (URL, optionnel)",
      },
      next: "Suivant",
      back: "Retour",
      submit: "Créer mon compte",
      submitting: "Création…",
      alreadyAccount: "Déjà un compte ?",
      signIn: "Se connecter",
      success: {
        title: "Compte créé 🎉",
        message:
          "Un email de confirmation a été envoyé à {{email}}. Cliquez sur le lien qu'il contient pour activer votre compte.",
        resendPrompt: "Vous n'avez rien reçu ? Renvoyer l'email",
        resent: "Email renvoyé, vérifiez votre boîte.",
      },
      errors: {
        createFailed: "La création du compte a échoué.",
        sendFailed: "L'envoi a échoué.",
      },
    },

    confirm: {
      confirming: "Confirmation en cours…",
      success: {
        title: "Compte confirmé ✅",
        message:
          "Vos identifiants vous ont été envoyés par email. Vous pouvez maintenant vous connecter.",
        signIn: "Se connecter",
      },
      error: {
        title: "Confirmation impossible",
        invalidLink: "Lien de confirmation invalide.",
        default: "La confirmation a échoué.",
      },
      resend: {
        prompt:
          "Lien expiré ou invalide ? Renvoyez-vous un email de confirmation :",
        submit: "Renvoyer l'email de confirmation",
        submitting: "Envoi…",
        sent: "Un nouvel email de confirmation vient d'être envoyé.",
        failed: "L'envoi a échoué.",
      },
      backToLogin: "Retour à la connexion",
    },

    dashboard: {
      greeting: "Bienvenue",
      subtitle:
        "Votre tableau de bord de production arrive bientôt — tickets d'arrêt, intervenants et KPIs de l'usine.",
      signOut: "Se déconnecter",
    },
  },
};

export default fr;
