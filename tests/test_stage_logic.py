"""
Test approved quote pipeline stage logic.
CRITICAL: This tests the client-approved stage sync rules.
"""

import pytest
from src.transformers.quote_transformer import QuoteStageLogic


class TestQuoteStageLogic:
    """Test quote stage derivation and update logic."""

    def test_stage_derivation_ordered(self):
        """Test: Ordered=true → closedwon"""
        quote = {'Ordered': True, 'Expired': False, 'QuoteClosed': False, 'Quoted': True}
        assert QuoteStageLogic.get_stage_from_epicor(quote) == 'closedwon'

    def test_stage_derivation_expired(self):
        """Test: Expired=true → quote_expired"""
        quote = {'Ordered': False, 'Expired': True, 'QuoteClosed': False, 'Quoted': True}
        assert QuoteStageLogic.get_stage_from_epicor(quote) == 'quote_expired'

    def test_stage_derivation_closed_lost(self):
        """Test: QuoteClosed=true AND Ordered=false → closedlost"""
        quote = {'Ordered': False, 'Expired': False, 'QuoteClosed': True, 'Quoted': True}
        assert QuoteStageLogic.get_stage_from_epicor(quote) == 'closedlost'

    def test_stage_derivation_quoted(self):
        """Test: Quoted=true → quote_sent"""
        quote = {'Ordered': False, 'Expired': False, 'QuoteClosed': False, 'Quoted': True}
        assert QuoteStageLogic.get_stage_from_epicor(quote) == 'quote_sent'

    def test_stage_derivation_created(self):
        """Test: Default → quote_created"""
        quote = {'Ordered': False, 'Expired': False, 'QuoteClosed': False, 'Quoted': False}
        assert QuoteStageLogic.get_stage_from_epicor(quote) == 'quote_created'

    def test_new_deal_always_updates(self):
        """Test: New deal (None) always gets stage set"""
        assert QuoteStageLogic.should_update_stage(None, 'quote_created') == True

    def test_terminal_stage_always_updates(self):
        """Test: Terminal stages from Epicor always update"""
        assert QuoteStageLogic.should_update_stage('quote_sent', 'closedwon') == True
        assert QuoteStageLogic.should_update_stage('follow_up', 'closedlost') == True
        assert QuoteStageLogic.should_update_stage('quote_sent', 'quote_expired') == True

    def test_cannot_reopen_permanent_terminals(self):
        """Test: Cannot reopen Closed Won/Lost"""
        assert QuoteStageLogic.should_update_stage('closedwon', 'quote_sent') == False
        assert QuoteStageLogic.should_update_stage('closedlost', 'quote_created') == False

    def test_can_reactivate_expired(self):
        """Test: Can reactivate from Quote Expired (reversible terminal)"""
        assert QuoteStageLogic.should_update_stage('quote_expired', 'quote_created') == True

    def test_forward_only_movement(self):
        """Test: Only move forward, never backward"""
        assert QuoteStageLogic.should_update_stage('quote_created', 'quote_sent') == True
        assert QuoteStageLogic.should_update_stage('quote_sent', 'quote_created') == False
        assert QuoteStageLogic.should_update_stage('follow_up', 'quote_sent') == False

    def test_hubspot_only_stages_protected(self):
        """Test: HubSpot-only stages (Technical Review, Follow Up) are protected"""
        # If HubSpot is at Technical Review, Epicor can move it forward but not backward
        assert QuoteStageLogic.should_update_stage('technical_review', 'quote_sent') == True
        assert QuoteStageLogic.should_update_stage('technical_review', 'quote_created') == False
