-- Sport déclaré : correction des libellés ("Runing") et indicateur de pratique.

-- On récupère les sports déclarés sur le fichier "Données sportives"; chargé à l'aide de l'ingestion
-- On s'assure de ne récuperer seulement que les sports déclarés (non null) et de les stocker dans pratique_declaree
-- Par ailleurs, on transforme 'Runing' en 'Course à pied' pour que cela corresponde avec ce que l'on a définit comme 'Activité'
-- Le sport_declare devient n'est plus vide (C'est un champs vide dans raw.sports), pratique_declaree dit vrai ou faux (sport_declare)
-- La méthode trim() permet de nettoyer un champ en enlevant les caractères inutiles (espaces au début ou à la fin)
select
    id_salarie,
    case trim(pratique_sport)
        when 'Runing' then 'Course à pied'
        else nullif(trim(pratique_sport), '')
    end                                   as sport_declare,
    nullif(trim(pratique_sport), '') is not null as pratique_declaree
from {{ source('raw', 'sports') }}
