const fr = {
  translation: {
    tagline: "Gardez votre production en flux.",

    language: { fr: "Français", en: "English" },

    legal: {
      taxId: "Matricule fiscal :",
      lastUpdated: "Dernière mise à jour :",
      backToHome: "Retour à l'accueil",

      privacy: {
        title: "Politique de confidentialité",
        updated: "27 août 2026",
        sections: {
          controller: {
            heading: "Qui est responsable de vos données",
            body: "OptiFlow est édité et exploité par {{tradeName}} {{legalForm}}, dont le siège social est situé {{registeredOffice}}, matricule fiscal {{taxId}}.\n\n{{tradeName}} {{legalForm}} est responsable de traitement pour les données de compte, de contact et de facturation de ses clients. Pour les données d'exploitation qu'une usine enregistre dans OptiFlow, elle agit en qualité de sous-traitant, sur instruction de cette usine.\n\nPour toute question sur la présente politique, ou pour exercer vos droits, écrivez à {{contactEmail}} ou appelez le {{contactPhone}}.",
          },
          data: {
            heading: "Les données que nous collectons",
            body: "Données de compte : nom et prénom, adresse e-mail professionnelle, numéro de téléphone lorsque vous en renseignez un, rôle dans l'usine et organisation de rattachement.\n\nDonnées d'exploitation : les tickets d'arrêt que vous ouvrez, prenez en charge ou clôturez, les postes de travail, lignes de production et unités autonomes de production que vous configurez, ainsi que les horodatages de chaque étape du cycle de vie de l'arrêt.\n\nDonnées techniques : journaux de connexion, adresse IP, type de navigateur et d'appareil, et pages de l'application consultées.\n\nNous ne collectons aucune donnée sensible et n'utilisons jamais vos données à des fins publicitaires.",
          },
          purposes: {
            heading: "Pourquoi nous les utilisons",
            body: "Fournir le service : créer votre compte, vous authentifier et vous donner accès aux seules données de votre organisation.\n\nFaire fonctionner le flux de traitement des arrêts : notifier les intervenants concernés, suivre la prise en charge et la résolution, et calculer les KPI de votre usine.\n\nMaintenir la sécurité et la disponibilité du service : détecter les abus, diagnostiquer les incidents et conserver les journaux d'audit.\n\nAssurer le support et la facturation : répondre à vos demandes et gérer l'abonnement.",
          },
          basis: {
            heading: "Base légale",
            body: "Nous traitons vos données pour l'exécution du contrat qui nous lie à votre organisation, pour respecter nos obligations légales et comptables, et sur le fondement de notre intérêt légitime à préserver la sécurité du service. Lorsque le consentement est requis, il vous est demandé et vous pouvez le retirer à tout moment.",
          },
          retention: {
            heading: "Durée de conservation",
            body: "Les données de compte sont conservées pendant toute la durée de l'abonnement de votre organisation, puis 12 mois après son terme.\n\nLes données d'exploitation (tickets, KPI) sont conservées pendant la durée de l'abonnement et peuvent être exportées ou supprimées à la demande de votre organisation.\n\nLes journaux techniques sont conservés 12 mois.\n\nLes pièces comptables sont conservées pendant la durée imposée par la législation fiscale applicable.",
          },
          sharing: {
            heading: "Avec qui nous les partageons",
            body: "Nous ne vendons pas vos données et ne les transmettons à aucun tiers pour son propre compte.\n\nNous faisons appel aux sous-traitants suivants, chacun lié par contrat et agissant sur nos seules instructions :\n\n· Google Cloud (Firestore, Pub/Sub, Cloud Tasks, Cloud Run) — hébergement et stockage des données, en région europe-west1.\n· Resend — envoi des e-mails transactionnels : confirmation de compte et notifications d'arrêt.\n\nNous pouvons également communiquer des données lorsque la loi ou une autorité compétente l'exige.",
          },
          security: {
            heading: "Sécurité",
            body: "Les données sont chiffrées en transit (HTTPS) et au repos par notre hébergeur. L'accès est réservé aux membres de votre organisation : chaque requête est cantonnée à votre espace et aucune donnée ne circule d'une usine à une autre.\n\nL'accès de nos équipes est limité à ce qui est strictement nécessaire à l'exploitation et au support du service.",
          },
          rights: {
            heading: "Vos droits",
            body: "Vous pouvez demander l'accès à vos données, leur rectification, leur suppression, une copie portable, ou la limitation de leur traitement. Vous pouvez également vous opposer à un traitement déterminé.\n\nAdressez votre demande à {{contactEmail}}. Nous répondons dans un délai d'un mois. Si vous relevez d'une organisation cliente, nous pouvons être amenés à lui transmettre votre demande : c'est elle qui décide du sort des données d'exploitation dont elle est responsable.",
          },
          cookies: {
            heading: "Cookies et stockage local",
            body: "OptiFlow n'utilise ni cookie publicitaire, ni traceur tiers.\n\nL'application web enregistre deux éléments dans le stockage local de votre navigateur : votre jeton de session, pour vous maintenir connecté, et votre préférence de langue. Effacer les données de votre navigateur supprime les deux et vous déconnecte.",
          },
          children: {
            heading: "Mineurs",
            body: "OptiFlow est un outil professionnel destiné au personnel des usines. Il ne s'adresse pas aux personnes de moins de 16 ans et ne doit pas être utilisé par elles.",
          },
          changes: {
            heading: "Modification de la présente politique",
            body: "Nous pouvons faire évoluer cette politique pour tenir compte des évolutions du service ou de la réglementation. La date figurant en haut de cette page indique toujours la version en vigueur, et toute modification substantielle est notifiée aux organisations clientes.",
          },
        },
      },

      terms: {
        title: "Conditions générales de vente",
        updated: "27 août 2026",
        sections: {
          purpose: {
            heading: "1. Objet",
            body: "Les présentes conditions générales de vente régissent la souscription au service OptiFlow et son utilisation. Le service est édité par {{tradeName}} {{legalForm}}, dont le siège social est situé {{registeredOffice}}, matricule fiscal {{taxId}} (l'« Éditeur »).\n\nElles sont acceptées par le client lors de la souscription et prévalent sur ses propres conditions d'achat.",
          },
          service: {
            heading: "2. Description du service",
            body: "OptiFlow est une plateforme logicielle en mode SaaS dédiée à la gestion des arrêts machine en milieu industriel. Elle couvre la détection de l'arrêt, la notification des intervenants, la prise en charge et le suivi du ticket, la validation du retour à la production et le calcul des KPI de l'usine.\n\nLe service s'utilise via une application web et une application mobile, sans installation sur les serveurs du client.",
          },
          account: {
            heading: "3. Comptes et accès",
            body: "Chaque organisation cliente dispose d'un espace isolé. Le client désigne un administrateur qui crée et gère les comptes utilisateurs et leurs rôles.\n\nLes identifiants sont personnels et confidentiels. Le client en assume l'usage et informe l'Éditeur sans délai de toute suspicion de compromission.",
          },
          subscription: {
            heading: "4. Souscription",
            body: "L'abonnement est souscrit pour le périmètre indiqué au devis ou au bon de commande accepté par le client : nombre d'utilisateurs, de sites et options retenues.\n\nToute extension de ce périmètre en cours de période est facturée au prorata, dans les mêmes conditions.",
          },
          pricing: {
            heading: "5. Prix",
            body: "Les prix sont ceux figurant au devis ou au bon de commande accepté par le client. Ils s'entendent hors taxes ; les taxes applicables s'ajoutent au taux en vigueur à la date de facturation.\n\nLes prix peuvent être révisés à chaque renouvellement. L'Éditeur en informe le client au moins 60 jours avant l'échéance ; le client peut alors résilier dans les conditions de l'article 7.",
          },
          payment: {
            heading: "6. Paiement",
            body: "Les factures sont payables à 30 jours date d'émission, par virement bancaire, sauf stipulation contraire du bon de commande.\n\nToute somme impayée à l'échéance porte intérêt de retard au taux légal, sans mise en demeure préalable. Après une relance restée sans réponse pendant 15 jours, l'Éditeur peut suspendre l'accès jusqu'au règlement.",
          },
          duration: {
            heading: "7. Durée et résiliation",
            body: "L'abonnement est conclu pour la durée indiquée au bon de commande et se renouvelle par périodes de même durée, sauf résiliation notifiée par écrit par l'une des parties au moins 30 jours avant le terme de la période en cours.\n\nChaque partie peut résilier en cas de manquement grave de l'autre non réparé dans les 30 jours suivant une mise en demeure écrite.\n\nÀ la fin du contrat, le client dispose de 30 jours pour exporter ses données. Passé ce délai, elles sont supprimées dans les conditions prévues par la politique de confidentialité.",
          },
          obligations: {
            heading: "8. Obligations du client",
            body: "Le client s'engage à utiliser le service conformément aux présentes conditions et à la réglementation applicable, à fournir des informations exactes, à tenir à jour ses comptes utilisateurs, et à ne pas tenter de contourner les mesures techniques protégeant le service ni d'accéder aux données d'une autre organisation.\n\nLe client est responsable des contenus qu'il enregistre dans le service et de l'information de son propre personnel sur les traitements réalisés.",
          },
          availability: {
            heading: "9. Disponibilité et support",
            body: "L'Éditeur met en œuvre les moyens nécessaires pour assurer la disponibilité du service 24 h/24, hors opérations de maintenance planifiées — annoncées à l'avance dans la mesure du possible — et hors défaillance d'un prestataire tiers ou de la connexion du client.\n\nLe support est joignable les jours ouvrés à {{contactEmail}} et au {{contactPhone}}. Tout engagement spécifique de disponibilité ou de délai de réponse est celui figurant au bon de commande.",
          },
          liability: {
            heading: "10. Responsabilité",
            body: "L'Éditeur est tenu d'une obligation de moyens. Sa responsabilité est limitée aux dommages directs et, toutes causes confondues, au montant des sommes versées par le client au cours des douze mois précédant le fait générateur.\n\nL'Éditeur n'est pas responsable des dommages indirects, notamment perte de production, perte de chiffre d'affaires ou perte de données résultant d'une cause extérieure à son contrôle.\n\nOptiFlow est un outil de gestion et de traçabilité. Il ne se substitue ni aux procédures de sécurité du client, ni à ses obligations réglementaires relatives à ses équipements.",
          },
          intellectualProperty: {
            heading: "11. Propriété intellectuelle",
            body: "Le service, ses logiciels, ses interfaces et sa documentation demeurent la propriété exclusive de l'Éditeur. L'abonnement confère un droit d'usage non exclusif et non cessible, pour la durée de l'abonnement et pour les seuls besoins internes du client.\n\nLes données enregistrées par le client restent sa propriété.",
          },
          dataProtection: {
            heading: "12. Données à caractère personnel",
            body: "Chaque partie respecte la législation applicable en matière de données à caractère personnel. Les traitements réalisés par l'Éditeur sont décrits dans la politique de confidentialité, qui fait partie intégrante des présentes conditions.",
          },
          law: {
            heading: "13. Droit applicable et litiges",
            body: "Les présentes conditions sont soumises au droit tunisien.\n\nLes parties s'efforcent de régler à l'amiable tout différend. À défaut d'accord dans un délai de 30 jours, le litige relève de la compétence exclusive des tribunaux de Sousse, Tunisie.",
          },
        },
      },
    },

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
        division: {
          general: "Général",
          bottleneck: "Goulot",
          critical: "Critique",
        },
        severity: {
          rank1: "Gravité la plus forte",
          rank2: "Gravité moindre",
        },
        shareOfTotal: "part du temps d'arrêt total",
        downtimeRemainder:
          "Parts du temps d'arrêt total ; le reste est sur des postes standards.",
        countSliceHint:
          "Un arrêt touchant plusieurs types de postes compte une fois dans chaque division.",
        mttrSliceHint:
          "Trois moyennes indépendantes — elles ne s'additionnent pas.",
        mtbfSliceHint:
          "Trois moyennes indépendantes — elles ne s'additionnent pas.",
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

    deleteDialog: {
      alsoDeleted:
        "Les éléments suivants seront également supprimés définitivement :",
      linesCount: "{{count}} ligne de production",
      linesCount_other: "{{count}} lignes de production",
      stationsCount: "{{count}} poste de travail",
      stationsCount_other: "{{count}} postes de travail",
      andMore: "et {{count}} autre",
      andMore_other: "et {{count}} autres",
      irreversible:
        "Cette action est définitive. Les éléments supprimés ne peuvent pas être récupérés.",
      cancel: "Annuler",
      confirm: "Supprimer définitivement",
      deleting: "Suppression…",
    },

    lines: {
      title: "Lignes de production",
      add: "Ajouter une ligne de production",
      empty: "Aucune ligne de production pour le moment.",
      noResults: "Aucune ligne de production ne correspond à votre recherche.",
      loading: "Chargement…",
      edit: "Modifier",
      independent: "Indépendante",
      filters: {
        search: "Rechercher",
        searchPlaceholder: "Rechercher par nom…",
        zoneArea: "Zone",
        allZoneAreas: "Toutes les zones",
      },
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
        independent: "Indépendante (aucune zone)",
        save: "Enregistrer",
        creating: "Création…",
        saving: "Enregistrement…",
        cancel: "Annuler",
        delete: "Supprimer",
        deleting: "Suppression…",
        confirmDelete: {
          title: "Supprimer cette ligne de production ?",
          body: "« {{name}} » sera supprimée définitivement.",
        },
        loadError: "Impossible de charger la ligne de production.",
        saveError: "Impossible d'enregistrer la ligne de production.",
        deleteError: "Impossible de supprimer la ligne de production.",
      },
    },

    stations: {
      title: "Postes de travail",
      add: "Ajouter un poste de travail",
      empty: "Aucun poste de travail pour le moment.",
      noResults: "Aucun poste de travail ne correspond à votre recherche.",
      loading: "Chargement…",
      edit: "Modifier",
      independent: "Indépendant",
      filters: {
        search: "Rechercher",
        searchPlaceholder: "Rechercher par nom…",
        type: "Type",
        allTypes: "Tous les types",
        line: "Ligne de production",
        allLines: "Toutes les lignes de production",
      },
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
        confirmDelete: {
          title: "Supprimer ce poste de travail ?",
          body: "« {{name}} » sera supprimé définitivement.",
        },
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
        confirmDelete: {
          title: "Supprimer cette zone de production ?",
          body: "« {{name}} » sera supprimée définitivement.",
        },
        loadError: "Impossible de charger la zone de production.",
        saveError: "Impossible d'enregistrer la zone de production.",
        deleteError: "Impossible de supprimer la zone de production.",
      },
    },

    users: {
      title: "Utilisateurs",
      add: "Ajouter un utilisateur",
      empty: "Aucun utilisateur pour le moment.",
      noResults: "Aucun utilisateur ne correspond à votre recherche.",
      loading: "Chargement…",
      edit: "Modifier",
      filters: {
        search: "Rechercher",
        searchPlaceholder: "Rechercher par nom ou prénom…",
      },
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
        passwordNoEmailHint:
          "Sans e-mail, ce compte se connecte depuis l'application mobile avec son code de sécurité : aucun mot de passe n'est nécessaire.",
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
