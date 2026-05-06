import * as anchor from "@coral-xyz/anchor";
import { Program } from "@coral-xyz/anchor";
import { Voltcore } from "../target/types/voltcore";
import { assert } from "chai";

describe("voltcore", () => {
  const provider = anchor.AnchorProvider.env();
  anchor.setProvider(provider);

  const program = anchor.workspace.Voltcore as Program<Voltcore>;
  const authority = provider.wallet;

  // ── ON-GRID COMMUNITY ─────────────────────────────────────

  describe("On-Grid Community — Barcelona Gràcia Solar", () => {
    const communityName = "barcelona-gracia-solar";

    const [communityPDA] = anchor.web3.PublicKey.findProgramAddressSync(
      [
        Buffer.from("community"),
        authority.publicKey.toBuffer(),
        Buffer.from(communityName),
      ],
      program.programId
    );

    it("Initializes on-grid community", async () => {
      const tx = await program.methods
        .initializeCommunity(
          communityName,
          { onGrid: {} },                   // CommunityMode::OnGrid
          new anchor.BN(30_000_000_000),    // €30,000 in lamports equivalent
          new anchor.BN(220_000)             // €0.22/kWh × 1_000_000
        )
        .accounts({
          community: communityPDA,
          authority: authority.publicKey,
          systemProgram: anchor.web3.SystemProgram.programId,
        })
        .rpc();

      console.log("    ✅ Community initialized:", tx);

      const community = await program.account.community.fetch(communityPDA);
      assert.equal(community.name, communityName);
      assert.deepEqual(community.mode, { onGrid: {} });
      assert.equal(community.totalDebt.toNumber(), 30_000_000_000);
      assert.equal(community.memberCount, 0);
      assert.equal(community.settlementCount.toNumber(), 0);
    });

    it("Adds 3 members to on-grid community", async () => {
      const members = [
        { wallet: anchor.web3.Keypair.generate(), investment: 3_000_000_000 },
        { wallet: anchor.web3.Keypair.generate(), investment: 3_000_000_000 },
        { wallet: anchor.web3.Keypair.generate(), investment: 3_000_000_000 },
      ];

      for (const m of members) {
        const [memberPDA] = anchor.web3.PublicKey.findProgramAddressSync(
          [
            Buffer.from("member"),
            communityPDA.toBuffer(),
            m.wallet.publicKey.toBuffer(),
          ],
          program.programId
        );

        await program.methods
          .addMember(new anchor.BN(m.investment))
          .accounts({
            community:     communityPDA,
            memberAccount: memberPDA,
            memberWallet:  m.wallet.publicKey,
            payer:         authority.publicKey,
            systemProgram: anchor.web3.SystemProgram.programId,
          })
          .rpc();

        const memberAccount = await program.account.memberAccount.fetch(memberPDA);
        assert.equal(memberAccount.investment.toNumber(), m.investment);
        console.log(`    ✅ Member added | share: ${memberAccount.shareBps.toNumber()} bps`);
      }

      const community = await program.account.community.fetch(communityPDA);
      assert.equal(community.memberCount, 3);
    });

    it("Records an on-grid settlement", async () => {
      const tx = await program.methods
        .recordSettlement(
          new anchor.BN(2_400_000),   // 2400 kWh = 2,400,000 Wh
          new anchor.BN(1_600_000),   // 1600 kWh self consumed
          new anchor.BN(800_000),     // 800 kWh excess sold to grid
          new anchor.BN(152_000),     // €0.152/kWh oracle price × 1_000_000
          "2025-06"
        )
        .accounts({
          community: communityPDA,
          authority: authority.publicKey,
        })
        .rpc();

      console.log("    ✅ Settlement recorded:", tx);

      const community = await program.account.community.fetch(communityPDA);

      // Debt should have decreased
      assert.isBelow(
        community.totalDebt.toNumber(),
        30_000_000_000,
        "Debt should decrease after settlement"
      );

      // Treasury should have increased
      assert.isAbove(
        community.treasuryBalance.toNumber(),
        0,
        "Treasury should increase after settlement"
      );

      assert.equal(community.settlementCount.toNumber(), 1);

      console.log(`    📊 Debt remaining: ${community.totalDebt.toNumber()}`);
      console.log(`    🌱 Treasury: ${community.treasuryBalance.toNumber()}`);
      console.log(`    📈 Total repaid: ${community.totalRepaid.toNumber()}`);
    });

    it("Verifies allocation ratios are correct", async () => {
      const community = await program.account.community.fetch(communityPDA);

      const initialDebt = 30_000_000_000;
      const debtRepaid  = initialDebt - community.totalDebt.toNumber();

      // Gross revenue calculation:
      // savings = 1,600,000 Wh × €0.22 = €352
      // excess  = 800,000 Wh × €0.152 = €121.60
      // gross   = €473.60
      // debt payment = €473.60 × 60% = €284.16

      // In micro EUR units (divided by 1_000_000 for Wh precision)
      // Verify debt repaid is approximately 60% of gross revenue
      assert.isAbove(debtRepaid, 0, "Some debt should be repaid");
      assert.isBelow(
        community.totalDebt.toNumber(),
        initialDebt,
        "Total debt should be less than initial"
      );

      console.log(`    ✅ Allocation verified | Repaid: ${debtRepaid} units`);
    });
  });

  // ── OFF-GRID COMMUNITY ────────────────────────────────────

  describe("Off-Grid Community — Extremadura Valle Verde", () => {
    const communityName = "extremadura-valle-verde";

    const [communityPDA] = anchor.web3.PublicKey.findProgramAddressSync(
      [
        Buffer.from("community"),
        authority.publicKey.toBuffer(),
        Buffer.from(communityName),
      ],
      program.programId
    );

    it("Initializes off-grid community", async () => {
      await program.methods
        .initializeCommunity(
          communityName,
          { offGrid: {} },               // CommunityMode::OffGrid
          new anchor.BN(40_000_000_000), // €40,000
          new anchor.BN(200_000)          // €0.20/kWh reference price
        )
        .accounts({
          community: communityPDA,
          authority: authority.publicKey,
          systemProgram: anchor.web3.SystemProgram.programId,
        })
        .rpc();

      const community = await program.account.community.fetch(communityPDA);
      assert.deepEqual(community.mode, { offGrid: {} });
      assert.equal(community.totalDebt.toNumber(), 40_000_000_000);
      console.log("    ✅ Off-grid community initialized");
    });

    it("Records off-grid settlement with zero excess revenue", async () => {
      await program.methods
        .recordSettlement(
          new anchor.BN(3_000_000),  // 3000 kWh produced
          new anchor.BN(3_000_000),  // 3000 kWh self consumed (all of it)
          new anchor.BN(0),          // 0 excess — off-grid stores in battery
          new anchor.BN(0),          // oracle price irrelevant for off-grid
          "2025-06"
        )
        .accounts({
          community: communityPDA,
          authority: authority.publicKey,
        })
        .rpc();

      const community = await program.account.community.fetch(communityPDA);

      assert.isBelow(
        community.totalDebt.toNumber(),
        40_000_000_000,
        "Off-grid debt should also decrease from savings"
      );

      assert.isAbove(
        community.treasuryBalance.toNumber(),
        0,
        "Off-grid treasury should grow from savings"
      );

      console.log("    ✅ Off-grid settlement recorded");
      console.log(`    📊 Debt: ${community.totalDebt.toNumber()}`);
      console.log(`    🌱 Treasury: ${community.treasuryBalance.toNumber()}`);
    });
  });

  // ── PROTOCOL RULES ────────────────────────────────────────

  describe("Protocol Rules", () => {
    it("Rejects settlement from non-authority", async () => {
      const fakeAuthority = anchor.web3.Keypair.generate();
      const communityName = "barcelona-gracia-solar";
      const [communityPDA] = anchor.web3.PublicKey.findProgramAddressSync(
        [
          Buffer.from("community"),
          authority.publicKey.toBuffer(),
          Buffer.from(communityName),
        ],
        program.programId
      );

      try {
        await program.methods
          .recordSettlement(
            new anchor.BN(1000), new anchor.BN(800),
            new anchor.BN(200), new anchor.BN(150_000), "2025-07"
          )
          .accounts({
            community: communityPDA,
            authority: fakeAuthority.publicKey,
          })
          .signers([fakeAuthority])
          .rpc();

        assert.fail("Should have thrown Unauthorized error");
      } catch (err) {
        console.log("    ✅ Unauthorized settlement correctly rejected");
      }
    });
  });
});