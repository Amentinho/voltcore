use anchor_lang::prelude::*;

declare_id!("VoLtC0reXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX");

// ─────────────────────────────────────────────
// CONSTANTS
// ─────────────────────────────────────────────

const DEBT_REPAYMENT_BPS: u64 = 6000;  // 60% in basis points
const TREASURY_BPS: u64       = 1500;  // 15%
const OPERATIONS_BPS: u64     = 2000;  // 20%
const PROTOCOL_FEE_BPS: u64   = 500;   // 5%
const MAX_MEMBERS: usize      = 20;
const BPS_DENOMINATOR: u64    = 10000;

// ─────────────────────────────────────────────
// PROGRAM
// ─────────────────────────────────────────────

#[program]
pub mod voltcore {
    use super::*;

    /// Initialize a new energy community (on-grid or off-grid)
    pub fn initialize_community(
        ctx: Context<InitializeCommunity>,
        name: String,
        mode: CommunityMode,
        total_investment_lamports: u64,
        reference_price_micro_eur: u64,   // price × 1_000_000 to avoid floats
    ) -> Result<()> {
        let community = &mut ctx.accounts.community;

        community.authority         = ctx.accounts.authority.key();
        community.name              = name;
        community.mode              = mode;
        community.total_investment  = total_investment_lamports;
        community.total_debt        = total_investment_lamports;
        community.total_repaid      = 0;
        community.treasury_balance  = 0;
        community.total_yield       = 0;
        community.reference_price   = reference_price_micro_eur;
        community.member_count      = 0;
        community.settlement_count  = 0;
        community.created_at        = Clock::get()?.unix_timestamp;
        community.bump              = ctx.bumps.community;

        emit!(CommunityCreated {
            community: community.key(),
            authority: community.authority,
            name: community.name.clone(),
            mode: community.mode.clone(),
            total_investment: community.total_investment,
        });

        msg!("VOLTCORE: Community '{}' initialized [{:?}]", community.name, community.mode);
        Ok(())
    }

    /// Add a member to the community with their investment share
    pub fn add_member(
        ctx: Context<AddMember>,
        investment_lamports: u64,
    ) -> Result<()> {
        let community = &mut ctx.accounts.community;
        let member    = &mut ctx.accounts.member_account;

        require!(
            community.member_count < MAX_MEMBERS as u8,
            VoltcoreError::CommunityFull
        );

        // Calculate share in basis points (10000 = 100%)
        let share_bps = investment_lamports
            .checked_mul(BPS_DENOMINATOR)
            .unwrap()
            .checked_div(community.total_investment)
            .unwrap();

        member.community    = community.key();
        member.wallet       = ctx.accounts.member_wallet.key();
        member.investment   = investment_lamports;
        member.share_bps    = share_bps;
        member.debt_repaid  = 0;
        member.yield_earned = 0;
        member.joined_at    = Clock::get()?.unix_timestamp;
        member.bump         = ctx.bumps.member_account;

        community.member_count += 1;

        emit!(MemberAdded {
            community: community.key(),
            member_wallet: member.wallet,
            investment: member.investment,
            share_bps: member.share_bps,
        });

        msg!(
            "VOLTCORE: Member {} joined with {} lamports ({} bps share)",
            member.wallet,
            investment_lamports,
            share_bps
        );
        Ok(())
    }

    /// Record an energy settlement period
    /// Called by the AI agent after reading meter data + oracle price
    pub fn record_settlement(
        ctx: Context<RecordSettlement>,
        production_wh: u64,           // Watt-hours produced
        self_consumption_wh: u64,     // Watt-hours self consumed
        excess_wh: u64,               // Watt-hours sold to grid (on-grid) or stored (off-grid)
        oracle_price_micro_eur: u64,  // Spot price × 1_000_000
        period: String,               // "2025-06"
    ) -> Result<()> {
        let community = &mut ctx.accounts.community;

        require!(
            ctx.accounts.authority.key() == community.authority,
            VoltcoreError::Unauthorized
        );

        // ── CALCULATE REVENUE ──────────────────────────────────

        // Savings = self_consumption × reference_price
        let savings_micro = self_consumption_wh
            .checked_mul(community.reference_price)
            .unwrap()
            .checked_div(1_000_000)
            .unwrap();

        // Excess revenue = excess × oracle_price (on-grid only)
        let excess_revenue_micro = match community.mode {
            CommunityMode::OnGrid => excess_wh
                .checked_mul(oracle_price_micro_eur)
                .unwrap()
                .checked_div(1_000_000)
                .unwrap(),
            CommunityMode::OffGrid => 0,
        };

        let gross_revenue = savings_micro
            .checked_add(excess_revenue_micro)
            .unwrap();

        // ── ALLOCATE REVENUE ───────────────────────────────────

        let debt_payment = gross_revenue
            .checked_mul(DEBT_REPAYMENT_BPS)
            .unwrap()
            .checked_div(BPS_DENOMINATOR)
            .unwrap();

        let treasury_contribution = gross_revenue
            .checked_mul(TREASURY_BPS)
            .unwrap()
            .checked_div(BPS_DENOMINATOR)
            .unwrap();

        let protocol_fee = gross_revenue
            .checked_mul(PROTOCOL_FEE_BPS)
            .unwrap()
            .checked_div(BPS_DENOMINATOR)
            .unwrap();

        // ── UPDATE STATE ───────────────────────────────────────

        community.total_debt = community.total_debt
            .saturating_sub(debt_payment);

        community.total_repaid = community.total_repaid
            .checked_add(debt_payment)
            .unwrap();

        // ReFi yield (6% APY = 0.5% monthly)
        let monthly_yield = community.treasury_balance
            .checked_mul(50)
            .unwrap()
            .checked_div(10_000)
            .unwrap();

        community.treasury_balance = community.treasury_balance
            .checked_add(treasury_contribution)
            .unwrap()
            .checked_add(monthly_yield)
            .unwrap();

        community.total_yield = community.total_yield
            .checked_add(monthly_yield)
            .unwrap();

        community.settlement_count += 1;

        // ── EMIT EVENT (readable by frontend + indexers) ───────

        emit!(SettlementRecorded {
            community:             community.key(),
            period:                period.clone(),
            production_wh,
            self_consumption_wh,
            excess_wh,
            oracle_price_micro_eur,
            gross_revenue,
            debt_payment,
            treasury_contribution,
            protocol_fee,
            monthly_yield,
            debt_remaining:        community.total_debt,
            treasury_balance:      community.treasury_balance,
            settlement_count:      community.settlement_count,
        });

        msg!(
            "VOLTCORE: Settlement {} recorded | Revenue: {} | Debt payment: {} | Treasury: {}",
            period,
            gross_revenue,
            debt_payment,
            community.treasury_balance
        );

        Ok(())
    }

    /// Distribute yield to members proportionally
    pub fn distribute_yield(
        ctx: Context<DistributeYield>,
        amount: u64,
    ) -> Result<()> {
        let community = &mut ctx.accounts.community;
        let member    = &mut ctx.accounts.member_account;

        require!(
            community.treasury_balance >= amount,
            VoltcoreError::InsufficientTreasury
        );

        let member_yield = amount
            .checked_mul(member.share_bps)
            .unwrap()
            .checked_div(BPS_DENOMINATOR)
            .unwrap();

        member.yield_earned = member.yield_earned
            .checked_add(member_yield)
            .unwrap();

        community.treasury_balance = community.treasury_balance
            .saturating_sub(member_yield);

        emit!(YieldDistributed {
            community:    community.key(),
            member:       member.wallet,
            amount:       member_yield,
            share_bps:    member.share_bps,
        });

        msg!(
            "VOLTCORE: Yield {} distributed to {} ({} bps share)",
            member_yield,
            member.wallet,
            member.share_bps
        );

        Ok(())
    }

    /// Stake treasury into ReFi pool (Sunrise Stake integration)
    pub fn stake_to_refi(
        ctx: Context<StakeToRefi>,
        amount: u64,
    ) -> Result<()> {
        let community = &mut ctx.accounts.community;

        require!(
            ctx.accounts.authority.key() == community.authority,
            VoltcoreError::Unauthorized
        );

        require!(
            community.treasury_balance >= amount,
            VoltcoreError::InsufficientTreasury
        );

        // In production: CPI call to Sunrise Stake program
        // stake_sunrise_stake(ctx, amount)?;

        community.treasury_balance = community.treasury_balance
            .saturating_sub(amount);

        emit!(TreasuryStaked {
            community: community.key(),
            amount,
            treasury_remaining: community.treasury_balance,
        });

        msg!("VOLTCORE: {} lamports staked to ReFi pool", amount);
        Ok(())
    }
}

// ─────────────────────────────────────────────
// ACCOUNTS
// ─────────────────────────────────────────────

#[derive(Accounts)]
#[instruction(name: String, mode: CommunityMode)]
pub struct InitializeCommunity<'info> {
    #[account(
        init,
        payer = authority,
        space = Community::SIZE,
        seeds = [b"community", authority.key().as_ref(), name.as_bytes()],
        bump
    )]
    pub community: Account<'info, Community>,

    #[account(mut)]
    pub authority: Signer<'info>,

    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct AddMember<'info> {
    #[account(
        mut,
        seeds = [b"community", community.authority.as_ref(), community.name.as_bytes()],
        bump = community.bump
    )]
    pub community: Account<'info, Community>,

    #[account(
        init,
        payer = payer,
        space = MemberAccount::SIZE,
        seeds = [b"member", community.key().as_ref(), member_wallet.key().as_ref()],
        bump
    )]
    pub member_account: Account<'info, MemberAccount>,

    /// CHECK: Just storing the wallet address
    pub member_wallet: UncheckedAccount<'info>,

    #[account(mut)]
    pub payer: Signer<'info>,

    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct RecordSettlement<'info> {
    #[account(
        mut,
        seeds = [b"community", community.authority.as_ref(), community.name.as_bytes()],
        bump = community.bump
    )]
    pub community: Account<'info, Community>,

    pub authority: Signer<'info>,
}

#[derive(Accounts)]
pub struct DistributeYield<'info> {
    #[account(
        mut,
        seeds = [b"community", community.authority.as_ref(), community.name.as_bytes()],
        bump = community.bump
    )]
    pub community: Account<'info, Community>,

    #[account(
        mut,
        seeds = [b"member", community.key().as_ref(), member_account.wallet.as_ref()],
        bump = member_account.bump
    )]
    pub member_account: Account<'info, MemberAccount>,

    pub authority: Signer<'info>,
}

#[derive(Accounts)]
pub struct StakeToRefi<'info> {
    #[account(
        mut,
        seeds = [b"community", community.authority.as_ref(), community.name.as_bytes()],
        bump = community.bump
    )]
    pub community: Account<'info, Community>,

    pub authority: Signer<'info>,
}

// ─────────────────────────────────────────────
// STATE ACCOUNTS
// ─────────────────────────────────────────────

#[account]
pub struct Community {
    pub authority:        Pubkey,    // 32
    pub name:             String,    // 4 + 64
    pub mode:             CommunityMode, // 1
    pub total_investment: u64,       // 8
    pub total_debt:       u64,       // 8
    pub total_repaid:     u64,       // 8
    pub treasury_balance: u64,       // 8
    pub total_yield:      u64,       // 8
    pub reference_price:  u64,       // 8  (micro EUR)
    pub member_count:     u8,        // 1
    pub settlement_count: u64,       // 8
    pub created_at:       i64,       // 8
    pub bump:             u8,        // 1
}

impl Community {
    pub const SIZE: usize = 8   // discriminator
        + 32                    // authority
        + 4 + 64                // name string
        + 1                     // mode enum
        + 8 * 6                 // u64 fields
        + 1                     // member_count
        + 8                     // settlement_count
        + 8                     // created_at
        + 1;                    // bump
}

#[account]
pub struct MemberAccount {
    pub community:    Pubkey,   // 32
    pub wallet:       Pubkey,   // 32
    pub investment:   u64,      // 8
    pub share_bps:    u64,      // 8  (basis points, 10000 = 100%)
    pub debt_repaid:  u64,      // 8
    pub yield_earned: u64,      // 8
    pub joined_at:    i64,      // 8
    pub bump:         u8,       // 1
}

impl MemberAccount {
    pub const SIZE: usize = 8   // discriminator
        + 32 + 32               // pubkeys
        + 8 * 4                 // u64 fields
        + 8                     // joined_at
        + 1;                    // bump
}

// ─────────────────────────────────────────────
// TYPES
// ─────────────────────────────────────────────

#[derive(AnchorSerialize, AnchorDeserialize, Clone, Debug, PartialEq)]
pub enum CommunityMode {
    OnGrid,
    OffGrid,
}

// ─────────────────────────────────────────────
// EVENTS
// ─────────────────────────────────────────────

#[event]
pub struct CommunityCreated {
    pub community:        Pubkey,
    pub authority:        Pubkey,
    pub name:             String,
    pub mode:             CommunityMode,
    pub total_investment: u64,
}

#[event]
pub struct MemberAdded {
    pub community:     Pubkey,
    pub member_wallet: Pubkey,
    pub investment:    u64,
    pub share_bps:     u64,
}

#[event]
pub struct SettlementRecorded {
    pub community:              Pubkey,
    pub period:                 String,
    pub production_wh:          u64,
    pub self_consumption_wh:    u64,
    pub excess_wh:              u64,
    pub oracle_price_micro_eur: u64,
    pub gross_revenue:          u64,
    pub debt_payment:           u64,
    pub treasury_contribution:  u64,
    pub protocol_fee:           u64,
    pub monthly_yield:          u64,
    pub debt_remaining:         u64,
    pub treasury_balance:       u64,
    pub settlement_count:       u64,
}

#[event]
pub struct YieldDistributed {
    pub community: Pubkey,
    pub member:    Pubkey,
    pub amount:    u64,
    pub share_bps: u64,
}

#[event]
pub struct TreasuryStaked {
    pub community:          Pubkey,
    pub amount:             u64,
    pub treasury_remaining: u64,
}

// ─────────────────────────────────────────────
// ERRORS
// ─────────────────────────────────────────────

#[error_code]
pub enum VoltcoreError {
    #[msg("Community is full — maximum 20 members")]
    CommunityFull,
    #[msg("Unauthorized — only community authority can call this")]
    Unauthorized,
    #[msg("Insufficient treasury balance")]
    InsufficientTreasury,
    #[msg("Invalid member share — shares must sum to 10000 bps")]
    InvalidShare,
    #[msg("Debt already fully repaid")]
    DebtFullyRepaid,
}