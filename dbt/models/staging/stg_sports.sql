-- Sport déclaré : correction des libellés ("Runing") et indicateur de pratique.

select
    id_salarie,
    case trim(pratique_sport)
        when 'Runing' then 'Course à pied'
        else nullif(trim(pratique_sport), '')
    end                                   as sport_declare,
    nullif(trim(pratique_sport), '') is not null as pratique_declaree
from {{ source('raw', 'sports') }}
