"""initial schema

Revision ID: 20260306_0001
Revises: 
Create Date: 2026-03-06 07:15:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260306_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "leagues",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=280), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="scheduled"),
        sa.Column("market_scope", sa.String(length=120), nullable=False, server_default="Pacifica perpetuals"),
        sa.Column("rules_json", sa.JSON(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_leagues_name", "leagues", ["name"])
    op.create_index("ix_leagues_status", "leagues", ["status"])

    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("wallet_address", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=True),
        sa.Column("auth_provider", sa.String(length=32), nullable=False, server_default="privy"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("wallet_address", name="uq_users_wallet_address"),
    )
    op.create_index("ix_users_wallet_address", "users", ["wallet_address"], unique=True)

    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_audit_events_action", "audit_events", ["action"])

    op.create_table(
        "copy_relationships",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("follower_user_id", sa.String(length=36), nullable=False),
        sa.Column("source_user_id", sa.String(length=36), nullable=False),
        sa.Column("scale_bps", sa.Integer(), nullable=False, server_default="10000"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="active"),
        sa.Column("risk_ack_version", sa.String(length=24), nullable=False, server_default="v1"),
        sa.Column("max_notional_usd", sa.Float(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["follower_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["source_user_id"], ["users.id"]),
    )
    op.create_index("ix_copy_relationships_follower_user_id", "copy_relationships", ["follower_user_id"])
    op.create_index("ix_copy_relationships_source_user_id", "copy_relationships", ["source_user_id"])
    op.create_index("ix_copy_relationships_status", "copy_relationships", ["status"])

    op.create_table(
        "vaults",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("headline", sa.String(length=180), nullable=False, server_default=""),
        sa.Column("strategy_type", sa.String(length=64), nullable=False),
        sa.Column("strategy_description", sa.Text(), nullable=False),
        sa.Column("manager_name", sa.String(length=80), nullable=False, server_default="ClashX Studio"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="live"),
        sa.Column("risk_band", sa.String(length=24), nullable=False, server_default="moderate"),
        sa.Column("aum", sa.Float(), nullable=False, server_default="0"),
        sa.Column("perf_7d", sa.Float(), nullable=False, server_default="0"),
        sa.Column("perf_30d", sa.Float(), nullable=False, server_default="0"),
        sa.Column("minimum_deposit", sa.Float(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_vaults_name", "vaults", ["name"])
    op.create_index("ix_vaults_status", "vaults", ["status"])
    op.create_index("ix_vaults_strategy_type", "vaults", ["strategy_type"])

    op.create_table(
        "copy_execution_events",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("copy_relationship_id", sa.String(length=36), nullable=False),
        sa.Column("source_order_ref", sa.String(length=120), nullable=False),
        sa.Column("mirrored_order_ref", sa.String(length=120), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("size_source", sa.Float(), nullable=False, server_default="0"),
        sa.Column("size_mirrored", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="queued"),
        sa.Column("error_reason", sa.String(length=240), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["copy_relationship_id"], ["copy_relationships.id"]),
    )
    op.create_index("ix_copy_execution_events_copy_relationship_id", "copy_execution_events", ["copy_relationship_id"])
    op.create_index("ix_copy_execution_events_mirrored_order_ref", "copy_execution_events", ["mirrored_order_ref"])
    op.create_index("ix_copy_execution_events_source_order_ref", "copy_execution_events", ["source_order_ref"])
    op.create_index("ix_copy_execution_events_status", "copy_execution_events", ["status"])
    op.create_index("ix_copy_execution_events_symbol", "copy_execution_events", ["symbol"])

    op.create_table(
        "league_participants",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("league_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["league_id"], ["leagues.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_league_participants_league_id", "league_participants", ["league_id"])
    op.create_index("ix_league_participants_user_id", "league_participants", ["user_id"])

    op.create_table(
        "leaderboard_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("league_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("unrealized_pnl", sa.Float(), nullable=False, server_default="0"),
        sa.Column("realized_pnl", sa.Float(), nullable=False, server_default="0"),
        sa.Column("win_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["league_id"], ["leagues.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_leaderboard_snapshots_captured_at", "leaderboard_snapshots", ["captured_at"])
    op.create_index("ix_leaderboard_snapshots_league_id", "leaderboard_snapshots", ["league_id"])
    op.create_index("ix_leaderboard_snapshots_user_id", "leaderboard_snapshots", ["user_id"])

    op.create_table(
        "strategy_activity_records",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("vault_id", sa.String(length=36), nullable=False),
        sa.Column("action_type", sa.String(length=48), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["vault_id"], ["vaults.id"]),
    )
    op.create_index("ix_strategy_activity_records_action_type", "strategy_activity_records", ["action_type"])
    op.create_index("ix_strategy_activity_records_recorded_at", "strategy_activity_records", ["recorded_at"])
    op.create_index("ix_strategy_activity_records_vault_id", "strategy_activity_records", ["vault_id"])

    op.create_table(
        "vault_deposits",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("vault_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("share_units", sa.Float(), nullable=False, server_default="0"),
        sa.Column("tx_ref", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["vault_id"], ["vaults.id"]),
        sa.UniqueConstraint("tx_ref", name="uq_vault_deposits_tx_ref"),
    )
    op.create_index("ix_vault_deposits_tx_ref", "vault_deposits", ["tx_ref"], unique=True)
    op.create_index("ix_vault_deposits_user_id", "vault_deposits", ["user_id"])
    op.create_index("ix_vault_deposits_vault_id", "vault_deposits", ["vault_id"])

    op.create_table(
        "vault_positions",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("vault_id", sa.String(length=36), nullable=False),
        sa.Column("symbol", sa.String(length=24), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("size", sa.Float(), nullable=False, server_default="0"),
        sa.Column("entry_price", sa.Float(), nullable=False, server_default="0"),
        sa.Column("mark_price", sa.Float(), nullable=False, server_default="0"),
        sa.Column("pnl_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["vault_id"], ["vaults.id"]),
    )
    op.create_index("ix_vault_positions_symbol", "vault_positions", ["symbol"])
    op.create_index("ix_vault_positions_vault_id", "vault_positions", ["vault_id"])


def downgrade() -> None:
    op.drop_index("ix_vault_positions_vault_id", table_name="vault_positions")
    op.drop_index("ix_vault_positions_symbol", table_name="vault_positions")
    op.drop_table("vault_positions")

    op.drop_index("ix_vault_deposits_vault_id", table_name="vault_deposits")
    op.drop_index("ix_vault_deposits_user_id", table_name="vault_deposits")
    op.drop_index("ix_vault_deposits_tx_ref", table_name="vault_deposits")
    op.drop_table("vault_deposits")

    op.drop_index("ix_strategy_activity_records_vault_id", table_name="strategy_activity_records")
    op.drop_index("ix_strategy_activity_records_recorded_at", table_name="strategy_activity_records")
    op.drop_index("ix_strategy_activity_records_action_type", table_name="strategy_activity_records")
    op.drop_table("strategy_activity_records")

    op.drop_index("ix_leaderboard_snapshots_user_id", table_name="leaderboard_snapshots")
    op.drop_index("ix_leaderboard_snapshots_league_id", table_name="leaderboard_snapshots")
    op.drop_index("ix_leaderboard_snapshots_captured_at", table_name="leaderboard_snapshots")
    op.drop_table("leaderboard_snapshots")

    op.drop_index("ix_league_participants_user_id", table_name="league_participants")
    op.drop_index("ix_league_participants_league_id", table_name="league_participants")
    op.drop_table("league_participants")

    op.drop_index("ix_copy_execution_events_symbol", table_name="copy_execution_events")
    op.drop_index("ix_copy_execution_events_status", table_name="copy_execution_events")
    op.drop_index("ix_copy_execution_events_source_order_ref", table_name="copy_execution_events")
    op.drop_index("ix_copy_execution_events_mirrored_order_ref", table_name="copy_execution_events")
    op.drop_index("ix_copy_execution_events_copy_relationship_id", table_name="copy_execution_events")
    op.drop_table("copy_execution_events")

    op.drop_index("ix_vaults_strategy_type", table_name="vaults")
    op.drop_index("ix_vaults_status", table_name="vaults")
    op.drop_index("ix_vaults_name", table_name="vaults")
    op.drop_table("vaults")

    op.drop_index("ix_copy_relationships_status", table_name="copy_relationships")
    op.drop_index("ix_copy_relationships_source_user_id", table_name="copy_relationships")
    op.drop_index("ix_copy_relationships_follower_user_id", table_name="copy_relationships")
    op.drop_table("copy_relationships")

    op.drop_index("ix_audit_events_action", table_name="audit_events")
    op.drop_table("audit_events")

    op.drop_index("ix_users_wallet_address", table_name="users")
    op.drop_table("users")

    op.drop_index("ix_leagues_status", table_name="leagues")
    op.drop_index("ix_leagues_name", table_name="leagues")
    op.drop_table("leagues")
