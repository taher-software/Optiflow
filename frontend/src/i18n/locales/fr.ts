const fr = {
  translation: {
    tagline: "Gardez votre production en flux.",

    language: { fr: "Français", en: "English" },

    common: {
      showPassword: "Afficher le mot de passe",
      hidePassword: "Masquer le mot de passe",
      errors: {
        title: "Les données n'ont pas pu être chargées.",
        unreachable: "Impossible de contacter le serveur.",
        unreachableHint:
          "Le serveur est injoignable : aucune donnée n'a pu être récupérée. Vérifiez votre connexion, puis réessayez.",
        retry: "Réessayer",
      },
    },

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
        invalidCredentials: "Nom d'utilisateur ou mot de passe invalide.",
        notConfirmed:
          "Veuillez confirmer votre compte avant de vous connecter.",
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
      eyebrow: "Usine",
      title: "Tableau de bord de l'usine",
      subtitle:
        "KPIs des temps d'arrêt — cliquez une équipe, un endroit, un processus ou un type pour le décortiquer.",
      signOut: "Se déconnecter",
      loading: "Chargement…",
      empty: "Aucune donnée pour cette période.",
      exploreStats: "Explorer les stats",
      compareEpisodes: "Comparer deux épisodes",
      shiftN: "Équipe {{n}}",
      rowMeta: "{{count}} arrêts · MTTR {{mttr}}",
      paretoCumul: "cumul {{pct}} %",
      kpi: {
        downtime: "Temps d'arrêt",
        count: "Nombre d'arrêts",
        mttr: "MTTR",
        mtbf: "MTBF",
        downtimeHint:
          "Cumulé par poste de travail : un arrêt déclaré sur un ensemble (ligne, UAP, usine) compte pour chacun des postes qu'il immobilise.",
        mttrHint: "temps moyen de réparation",
        mtbfHint: "temps moyen entre pannes",
      },
      period: {
        today: "Aujourd'hui",
        "7d": "7 jours",
        "30d": "30 jours",
        custom: "Période…",
        from: "Du",
        to: "Au",
      },
      cards: {
        byShift: "Temps d'arrêt par équipe",
        byUap: "Temps d'arrêt par UAP",
        byLine: "Temps d'arrêt par ligne",
        byStation: "Temps d'arrêt par poste",
        pareto: "Causes d'arrêt par processus (Pareto)",
        repair: "Temps de réparation par processus",
        byType: "Temps d'arrêt par type",
        clickHint: "cliquez pour explorer",
        paretoHint: "cliquez pour le détail par intervenant",
        repairHint: "MTTR cumulé",
      },
      dimension: {
        shift: "Équipe",
        uap: "UAP",
        line: "Ligne de production",
        station: "Poste de travail",
        process: "Processus",
        type: "Type d'arrêt",
      },
      process: {
        maintenance: "Maintenance",
        production: "Production",
        quality: "Qualité",
        logistic: "Logistique",
      },
      types: {
        break_down: "Panne machine",
        quality_issue: "Défaut qualité",
        absenteeism: "Absentéisme",
        wip_shortage: "Rupture WIP",
        material_shortage: "Rupture composants",
        setup_changeover: "Setup / Changeover",
        others: "Autre",
      },
      filters: {
        process: "Processus",
        shift: "Équipe",
        allProcesses: "Tous processus",
        allShifts: "Toutes équipes",
      },
      drill: {
        root: "Usine",
        close: "Fermer",
        loading: "Chargement du détail…",
        associatedProcess: "Processus habituel :",
        childrenTitle: "Temps d'arrêt par endroit",
        locationsHint: "cliquez un endroit pour descendre dans la hiérarchie",
        linesHint: "cliquez une ligne pour descendre aux postes",
        noLinesHint: "cette UAP n'a pas de lignes — postes directement",
        stationsHint: "postes de cette ligne",
        mttrByAgent: "MTTR par intervenant",
        countByAgent: "Nombre d'arrêts par intervenant",
        downtimeByShift: "Temps d'arrêt par équipe",
        downtimeByType: "Temps d'arrêt par type",
      },
    },

    stats: {
      eyebrow: "Stats · Explorateur",
      title: "Explorer les données",
      subtitle:
        "Suivi journalier ou comparaison de deux épisodes — métrique, scope, processus, équipe et période.",
      mode: {
        follow: "Suivi journalier",
        compare: "⇄ Comparer deux épisodes",
      },
      metric: {
        duration: "Temps d'arrêt",
        count: "Nombre d'arrêts",
        mttr: "MTTR",
      },
      metricTitle: {
        duration: "Temps d'arrêt journalier",
        count: "Nombre d'arrêts par jour",
        mttr: "MTTR journalier",
      },
      filters: { scope: "Scope", wholePlant: "Usine (toutes)" },
      byShift: "Répartition par équipe",
      byProcess: "Répartition par processus",
      compare: {
        ep1: "Épisode 1",
        ep2: "Épisode 2",
        total1: "Total épisode 1",
        total2: "Total épisode 2",
        average1: "MTTR moyen épisode 1",
        average2: "MTTR moyen épisode 2",
        gap: "Écart",
        gapBasis: "{{latest}} (le plus récent) vs {{reference}}",
        gapUndefined: "{{reference}} est à zéro : écart non calculable",
        title: "Épisode 1 vs Épisode 2",
        axisHint:
          "Axe X : jour de l'épisode (J1 → Jn) — les deux périodes sont alignées par index de jour.",
      },
    },

    nav: {
      dashboard: "Tableau de bord",
      stats: "Stats",
      users: "Utilisateurs",
      uaps: "Zones de production",
      lines: "Lignes de production",
      stations: "Postes de travail",
      settings: "Paramètres",
    },

    settings: {
      title: "Paramètres de l'usine",
      subtitle:
        "Configurez l'organisation des équipes et le délai d'escalade des arrêts.",
      loading: "Chargement…",
      shiftNumber: {
        label: "Nombre d'équipes",
        help: "Nombre d'équipes (shifts) par jour. Par exemple, une usine fonctionnant 24h/24 avec trois équipes de 8 heures en compte 3.",
      },
      shift: {
        title: "Équipe {{number}}",
        window: "Fenêtre de travail",
        start: "Heure de début",
        end: "Heure de fin",
        break: "Pause (facultative)",
        breakStart: "Début de la pause",
        breakEnd: "Fin de la pause",
        breakHelp:
          "La pause est retirée de la fenêtre de l'équipe pour obtenir le temps planifié, qui sert au calcul du MTBF (temps moyen entre arrêts). Laissez les deux champs vides si l'équipe n'a pas de pause.",
        errors: {
          missingWindow:
            "Renseignez l'heure de début et l'heure de fin de l'équipe.",
          zeroLengthWindow:
            "L'heure de début et l'heure de fin de l'équipe doivent différer.",
          breakIncomplete:
            "Renseignez le début et la fin de la pause, ou laissez les deux champs vides.",
          breakOutsideWindow:
            "La pause doit être comprise dans la fenêtre de l'équipe.",
          breakLength:
            "La durée de la pause doit être supérieure à zéro et plus courte que la fenêtre de l'équipe.",
        },
      },
      escalate: {
        label: "Délai d'escalade (secondes)",
        help: "Durée pendant laquelle un arrêt peut rester non résolu avant d'être escaladé aux responsables. Par défaut 1800 secondes (30 minutes).",
        approx: "(≈ {{minutes}} min)",
      },
      save: "Enregistrer",
      saving: "Enregistrement…",
      saved: "Paramètres enregistrés.",
      saveError: "Impossible d'enregistrer les paramètres.",
    },

    lines: {
      title: "Lignes de production",
      add: "Ajouter une ligne de production",
      empty: "Aucune ligne de production pour le moment.",
      loading: "Chargement…",
      edit: "Modifier",
      table: {
        name: "Nom",
        zoneArea: "Zone",
        description: "Description",
        actions: "Actions",
      },
      form: {
        createTitle: "Nouvelle ligne de production",
        editTitle: "Modifier la ligne de production",
        name: "Nom",
        namePlaceholder: "ex. Ligne 1",
        description: "Description",
        descriptionPlaceholder: "Ce que produit cette ligne…",
        zoneArea: "Zone",
        zoneAreaPlaceholder: "Sélectionner une zone de production…",
        save: "Enregistrer",
        creating: "Création…",
        saving: "Enregistrement…",
        cancel: "Annuler",
        delete: "Supprimer",
        deleting: "Suppression…",
        confirmDelete:
          "Supprimer cette ligne de production ? Cette action est irréversible.",
        loadError: "Impossible de charger la ligne de production.",
        saveError: "Impossible d'enregistrer la ligne de production.",
        deleteError: "Impossible de supprimer la ligne de production.",
      },
    },

    stations: {
      title: "Postes de travail",
      add: "Ajouter un poste de travail",
      empty: "Aucun poste de travail pour le moment.",
      loading: "Chargement…",
      edit: "Modifier",
      independent: "Indépendant",
      types: {
        standard: "Standard",
        bottleneck: "Goulot d'étranglement",
        critical: "Critique",
      },
      table: {
        name: "Nom",
        type: "Type",
        line: "Ligne de production",
        actions: "Actions",
      },
      form: {
        createTitle: "Nouveau poste de travail",
        editTitle: "Modifier le poste de travail",
        name: "Nom",
        namePlaceholder: "ex. Poste A3",
        description: "Description",
        descriptionPlaceholder: "Ce que fait ce poste…",
        line: "Ligne de production",
        independent: "Indépendant (aucune ligne)",
        type: "Type",
        save: "Enregistrer",
        creating: "Création…",
        saving: "Enregistrement…",
        cancel: "Annuler",
        delete: "Supprimer",
        deleting: "Suppression…",
        confirmDelete:
          "Supprimer ce poste de travail ? Cette action est irréversible.",
        loadError: "Impossible de charger le poste de travail.",
        saveError: "Impossible d'enregistrer le poste de travail.",
        deleteError: "Impossible de supprimer le poste de travail.",
      },
    },

    uaps: {
      title: "Zones de production",
      add: "Ajouter une zone de production",
      empty: "Aucune zone de production pour le moment.",
      loading: "Chargement…",
      edit: "Modifier",
      memberCount: "{{count}} ressource",
      memberCount_other: "{{count}} ressources",
      form: {
        createTitle: "Nouvelle zone de production",
        editTitle: "Modifier la zone de production",
        name: "Nom",
        namePlaceholder: "ex. Ligne d'assemblage A",
        description: "Description",
        descriptionPlaceholder: "Ce que couvre cette zone…",
        resources: "Ressources affectées",
        noMembers: "Aucun utilisateur avec ce rôle pour le moment.",
        save: "Enregistrer",
        creating: "Création…",
        saving: "Enregistrement…",
        cancel: "Annuler",
        delete: "Supprimer",
        deleting: "Suppression…",
        confirmDelete:
          "Supprimer cette zone de production ? Cette action est irréversible.",
        loadError: "Impossible de charger la zone de production.",
        saveError: "Impossible d'enregistrer la zone de production.",
        deleteError: "Impossible de supprimer la zone de production.",
      },
    },

    users: {
      title: "Utilisateurs",
      add: "Ajouter un utilisateur",
      empty: "Aucun utilisateur pour le moment.",
      loading: "Chargement…",
      edit: "Modifier",
      table: {
        name: "Nom",
        role: "Rôle",
        email: "Email",
        securityCode: "Code de sécurité",
        actions: "Actions",
      },
      form: {
        createTitle: "Nouvel utilisateur",
        editTitle: "Modifier l'utilisateur",
        firstName: "Prénom",
        lastName: "Nom",
        role: "Rôle",
        roleLocked: "ne peut pas être modifié",
        email: "Email",
        optional: "optionnel",
        password: "Mot de passe",
        passwordEdit: "Nouveau mot de passe",
        passwordEditHint: "Laisser vide pour ne pas changer",
        save: "Enregistrer",
        creating: "Création…",
        saving: "Enregistrement…",
        cancel: "Annuler",
        loadError: "Impossible de charger l'utilisateur.",
        saveError: "Impossible d'enregistrer l'utilisateur.",
      },
      roles: {
        owner: {
          name: "Propriétaire",
          description:
            "Possède l'organisation. Accès illimité à toutes les fonctionnalités, la facturation, les abonnements, les paramètres de l'organisation, les sites, les utilisateurs et les permissions.",
        },
        admin: {
          name: "Administrateur",
          description:
            "Gère la configuration de l'organisation, les utilisateurs, les permissions, les sites, les structures de production et les paramètres système. Accès opérationnel complet, mais ne possède pas l'organisation.",
        },
        manager: {
          name: "Manager",
          description:
            "Responsable de département ou d'usine, en charge de la performance opérationnelle globale. Visibilité sur plusieurs ateliers, lignes de production et équipes, avec l'autorité de suivre les KPIs, allouer les ressources et prendre des décisions stratégiques.",
        },
        production_supervisor: {
          name: "Superviseur de production",
          description:
            "Supervise les activités de production sur un ou plusieurs ateliers. Coordonne les agents de production, suit la performance, résout les problèmes escaladés et garantit l'atteinte des objectifs de production.",
        },
        production_agent: {
          name: "Agent de production",
          description:
            "Responsable terrain de la production, en charge des opérations quotidiennes d'une zone de production. Peut représenter un chef d'équipe, un chef de poste, un responsable d'UAP, un responsable d'îlot ou tout responsable opérationnel gérant directement la production et signalant les incidents.",
        },
        quality_supervisor: {
          name: "Superviseur qualité",
          description:
            "Supervise les activités qualité, coordonne les agents qualité, valide les inspections, suit les KPIs qualité et assure la conformité aux normes qualité.",
        },
        quality_agent: {
          name: "Agent qualité",
          description:
            "Responsable terrain de la qualité, en charge des inspections, audits, gestion des non-conformités et activités de contrôle qualité dans une zone assignée.",
        },
        maintenance_supervisor: {
          name: "Superviseur maintenance",
          description:
            "Supervise les opérations de maintenance, priorise les interventions, coordonne les agents de maintenance et assure la fiabilité des équipements et la planification de la maintenance.",
        },
        maintenance_agent: {
          name: "Agent de maintenance",
          description:
            "Responsable terrain de la maintenance, en charge de coordonner les travaux de maintenance dans un atelier, une ligne de production ou une zone technique. Peut représenter un chef d'équipe maintenance ou un coordinateur de zone.",
        },
        logistic_supervisor: {
          name: "Superviseur logistique",
          description:
            "Supervise les opérations logistiques, les activités d'entrepôt, les flux de matières et coordonne les agents logistiques.",
        },
        logistic_agent: {
          name: "Agent logistique",
          description:
            "Responsable terrain de la logistique, en charge des opérations d'entrepôt, de l'approvisionnement, des expéditions, des réceptions ou des activités d'inventaire dans une zone assignée.",
        },
      },
    },
  },
};

export default fr;
