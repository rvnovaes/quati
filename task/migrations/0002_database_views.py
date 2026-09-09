# Views SQL usadas pelo dashboard (task/queries.py) e pelo model TaskFilterViewModel (managed=False).
# Definições recuperadas das migrations originais (0145 e 0148) antes da regeneração do histórico.
from django.db import migrations

DASHBOARD_VIEW_SQL = """
        CREATE OR REPLACE VIEW dashboard_view AS SELECT task.id,
            task.parent_id,
            task.task_number,
            task.create_date,
            task.alter_date,
            task.legacy_code,
            task.delegation_date,
            task.acceptance_date,
            task.final_deadline_date,
            task.execution_date,
            task.return_date,
            task.refused_date,
            task.alter_user_id,
            task.create_user_id,
            task.person_asked_by_id,
            task.person_company_representative_id,
            task.person_executed_by_id,
            task.movement_id,
            task.is_active,
            task.description,
            task.task_status,
            task.system_prefix,
            task.type_task_id,
            task.blocked_payment_date,
            task.finished_date,
            task.person_distributed_by_id,
            task.acceptance_service_date,
            task.refused_service_date,
            task.requested_date,
            person.name AS client,
            court_district.id AS court_district_id,
            state.id AS state_id,
            court_division.id AS court_division_id,
            type_task.name AS type_service,
            law_suit.law_suit_number,
            law_suit.opposing_party,
            task.office_id,	
            task_parent.task_number AS parent_task_number
        FROM ((((((((task
             JOIN movement ON ((task.movement_id = movement.id)))
             JOIN law_suit ON ((movement.law_suit_id = law_suit.id)))
             JOIN folder ON ((law_suit.folder_id = folder.id)))
             JOIN person ON ((folder.person_customer_id = person.id)))
             LEFT JOIN court_district ON ((law_suit.court_district_id = court_district.id)))
             LEFT JOIN state ON ((court_district.state_id = state.id)))
             LEFT JOIN court_division ON ((law_suit.court_division_id = court_division.id)))
             JOIN type_task ON ((task.type_task_id = type_task.id))
             LEFT JOIN task task_parent ON (task.parent_id = task_parent.id))
    """

TASK_FILTER_VIEW_SQL = """
        CREATE OR REPLACE VIEW task_filter_view 
        AS 
        SELECT task.id as id,
            task.acceptance_date as acceptance_date,
            task.acceptance_service_date as acceptance_service_date,
            task.alter_date as alter_date,
            task.alter_user_id as alter_user_id,
            task.amount as amount,
            task.price_category as price_category,
            COALESCE(parent_office.legal_name::text, person.legal_name::text) AS asked_by_legal_name,
            task.blocked_payment_date as blocked_payment_date,
            person.name AS client,
            court_district.id AS court_district_id,
            court_district.name AS court_district_name,
            court_division.id AS court_division_id,
            court_division.name AS court_division_name,
            task.create_date as create_date,
            task.create_user_id as create_user_id,
            task.delegation_date as delegation_date,
            task.description as description,
            COALESCE(task.person_executed_by_id, child_office.office_child_id) AS executed_by_id,
            COALESCE(task_person_executed_by.legal_name, child_office.legal_name) AS executed_by_legal_name,
            task.execution_date as execution_date,
            task.final_deadline_date as final_deadline_date,
            task.finished_date as finished_date,
            task.is_active as is_active,
            law_suit.law_suit_number as law_suit_number,
            task.legacy_code as legacy_code,
            task.movement_id as movement_id,
            task.office_id as office_id,
            task_office.legal_name as office_legal_name,
            law_suit.opposing_party as opposing_party,
            COALESCE(task_parent.task_number::text, task.legacy_code::text) AS origin_code,
            task.parent_id as parent_id,
            task_parent.task_number AS parent_task_number,
            task.person_asked_by_id as person_asked_by_id,
            task.person_company_representative_id as person_company_representative_id,
            task.person_distributed_by_id as person_distributed_by_id,
            task.person_executed_by_id as person_executed_by_id,
            task.refused_date as refused_date,
            task.refused_service_date as refused_service_date,
            task.requested_date as requested_date,
            task.return_date as return_date,
            state.id AS state_id,
            state.initials AS state_initials,
            task.system_prefix as system_prefix,
            task.task_hash as task_hash,
            task.task_number as task_number,
            task.task_status as task_status,
            task.type_task_id as type_task_id,
            type_task.name AS type_task_name
        FROM (
                (
                    (
                        (
                            (
                                (
                                    (
                                        (task
                                         JOIN core_office as task_office on task_office.id = task.office_id
                                         JOIN movement ON (
                                            (task.movement_id = movement.id)
                                        ))
                                    JOIN law_suit ON (
                                        (movement.law_suit_id = law_suit.id)
                                    ))
                                JOIN folder ON (
                                    (law_suit.folder_id = folder.id)
                                ))
                            JOIN person ON (
                                (folder.person_customer_id = person.id)
                            ))
                        LEFT JOIN court_district ON (
                            (law_suit.court_district_id = court_district.id)
                        ))
                    LEFT JOIN state ON (
                        (court_district.state_id = state.id)
                    ))
                LEFT JOIN court_division ON (
                    (law_suit.court_division_id = court_division.id)
                ))
            JOIN type_task ON (
                (task.type_task_id = type_task.id)
            )
            LEFT JOIN task AS task_parent ON (
                task.parent_id = task_parent.id)
            LEFT JOIN core_office AS parent_office ON (task_parent.office_id = parent_office.id)
            LEFT JOIN person as task_person_executed_by ON (task.person_executed_by_id = task_person_executed_by.id)
            LEFT JOIN (select sub3_task.id as sub_parent_id, MAX(sub4_task.id) as child_id 
                        from task as sub3_task 
                        inner join task as sub4_task on sub4_task.parent_id = sub3_task.id
                        where not sub3_task.task_status in ('Recusada pelo Service', 'Recusada')
                        group by sub3_task.id
                        ) as child_task on child_task.sub_parent_id = task.id
            LEFT JOIN(  
                select sub1_task.id as sub1_task_id, sub2_office.id as office_child_id, sub2_office.legal_name 
                    from task as sub1_task
                    inner join core_office as sub2_office on sub2_office.id = sub1_task.office_id 
                                            
            ) as child_office on child_office.sub1_task_id = child_task.child_id
        )
    """


class Migration(migrations.Migration):

    dependencies = [
        ('task', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL('DROP VIEW IF EXISTS dashboard_view;', migrations.RunSQL.noop),
        migrations.RunSQL(DASHBOARD_VIEW_SQL, 'DROP VIEW IF EXISTS dashboard_view;'),
        migrations.RunSQL('DROP VIEW IF EXISTS task_filter_view;', migrations.RunSQL.noop),
        migrations.RunSQL(TASK_FILTER_VIEW_SQL, 'DROP VIEW IF EXISTS task_filter_view;'),
    ]
