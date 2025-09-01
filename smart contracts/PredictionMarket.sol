// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/**
 * @title PredictionMarket
 * @author Your Project Name
 * @notice This contract manages pari-mutuel prediction markets for sports matches.
 * @dev It holds betting tokens in escrow, records user bets, and distributes winnings
 * based on results reported by a trusted Oracle. It uses DuckToken as the betting currency.
 */
contract PredictionMarket is Ownable, ReentrancyGuard {

    // --- State Variables ---

    /// @notice The ERC20 token used for placing bets (DuckToken).
    IERC20 public immutable bettingToken;

    /// @notice The trusted address that is authorized to create markets and report match results.
    address public oracle;

    /// @notice Defines the possible outcomes a user can predict for a match.
    enum Prediction { HOME_TEAM, AWAY_TEAM, DRAW }

    /// @notice Defines the lifecycle status of a betting market.
    enum MarketStatus { PENDING, OPEN, CLOSED, SETTLED }

    /// @notice Stores all on-chain information about a specific betting market.
    struct Match {
        uint256 matchId;       // The unique ID from the external sports API.
        MarketStatus status;   // The current status of the market.
        Prediction result;     // The final, winning outcome of the match.
        uint256 potHome;       // Total tokens bet on the home team.
        uint256 potAway;       // Total tokens bet on the away team.
        uint256 potDraw;       // Total tokens bet on a draw.
        uint256 totalPot;      // Sum of all three pots.
    }

    /// @notice Stores the details of a single bet placed by a user on a match.
    struct Bet {
        address user;          // The address of the bettor.
        Prediction prediction; // The user's predicted outcome.
        uint256 amount;        // The amount of tokens wagered.
    }

    /// @notice Maps a match ID to its on-chain market data.
    mapping(uint256 => Match) public markets;
    
    /// @notice Maps a match ID to a user's address to their specific bet.
    mapping(uint256 => mapping(address => Bet)) public bets;

    // --- Events ---

    event MarketCreated(uint256 indexed matchId);
    event BetPlaced(uint256 indexed matchId, address indexed user, Prediction prediction, uint256 amount);
    event ResultReported(uint256 indexed matchId, Prediction result);
    event WinningsClaimed(uint256 indexed matchId, address indexed user, uint256 amount);
    event OracleUpdated(address indexed newOracle);

    // --- Modifiers ---

    /// @dev Throws an error if the caller is not the designated Oracle.
    modifier onlyOracle() {
        require(msg.sender == oracle, "Caller is not the Oracle");
        _;
    }

    // --- Functions ---

    /**
     * @notice Contract constructor.
     * @dev Sets the betting token address and initializes the deployer as the first Oracle and Owner.
     * @param _tokenAddress The address of the DuckToken ERC20 contract.
     */
    constructor(address _tokenAddress) Ownable(msg.sender) {
        bettingToken = IERC20(_tokenAddress);
        oracle = msg.sender;
    }

    /**
     * @notice Allows the contract owner to update the Oracle address.
     * @dev It's critical to have this function to be able to rotate the Oracle key if it is ever compromised.
     * @param _newOracle The address of the new Oracle.
     */
    function setOracle(address _newOracle) external onlyOwner {
        require(_newOracle != address(0), "Cannot set Oracle to the zero address");
        oracle = _newOracle;
        emit OracleUpdated(_newOracle);
    }

    /**
     * @notice Creates a new prediction market for a given match.
     * @dev Can only be called by the Oracle. Initializes the market struct.
     * @param _matchId The unique ID of the match from the external sports API.
     */
    function createMarket(uint256 _matchId) external onlyOracle {
        require(markets[_matchId].matchId == 0, "Market already exists");
        markets[_matchId] = Match({
            matchId: _matchId,
            status: MarketStatus.OPEN,
            result: Prediction.HOME_TEAM, // A default value, irrelevant until settled.
            potHome: 0,
            potAway: 0,
            potDraw: 0,
            totalPot: 0
        });
        emit MarketCreated(_matchId);
    }
    
    /**
     * @notice Places a bet on an open market.
     * @dev User must have first approved the contract to spend their DuckTokens.
     * Protected against re-entrancy attacks.
     * @param _matchId The ID of the match to bet on.
     * @param _prediction The user's predicted outcome (0=HOME, 1=AWAY, 2=DRAW).
     * @param _amount The amount of DuckTokens to bet.
     */
    function placeBet(uint256 _matchId, Prediction _prediction, uint256 _amount) external nonReentrant {
        require(_amount > 0, "Bet amount must be greater than zero");
        Match storage currentMarket = markets[_matchId];
        require(currentMarket.status == MarketStatus.OPEN, "Market is not open");
        require(bets[_matchId][msg.sender].amount == 0, "User has already placed a bet on this match");

        // Interaction: Pull tokens from user to this contract for escrow.
        bool success = bettingToken.transferFrom(msg.sender, address(this), _amount);
        require(success, "Token transfer failed. Check your approval.");

        // Effects: Update market state.
        if (_prediction == Prediction.HOME_TEAM) currentMarket.potHome += _amount;
        else if (_prediction == Prediction.AWAY_TEAM) currentMarket.potAway += _amount;
        else currentMarket.potDraw += _amount;
        currentMarket.totalPot += _amount;
        
        bets[_matchId][msg.sender] = Bet(msg.sender, _prediction, _amount);

        emit BetPlaced(_matchId, msg.sender, _prediction, _amount);
    }
    
    /**
     * @notice Reports the final result of a match, settling the market.
     * @dev Can only be called by the Oracle. This is the action that closes betting and determines the winners.
     * @param _matchId The ID of the match to settle.
     * @param _result The final winning outcome.
     */
    function reportResult(uint256 _matchId, Prediction _result) external onlyOracle {
        Match storage currentMarket = markets[_matchId];
        // It's possible to close a market before settling, so we check it is not already settled.
        require(currentMarket.status != MarketStatus.SETTLED, "Market is already settled");
        currentMarket.status = MarketStatus.SETTLED;
        currentMarket.result = _result;
        emit ResultReported(_matchId, _result);
    }

    /**
     * @notice Allows a winning user to claim their share of the prize pool.
     * @dev Calculates the user's proportional winnings and transfers the tokens.
     * Protected against re-entrancy. The user's bet amount is zeroed out to prevent double-claiming.
     * @param _matchId The ID of the settled match from which to claim.
     */
    function claimWinnings(uint256 _matchId) external nonReentrant {
        Match storage currentMarket = markets[_matchId];
        require(currentMarket.status == MarketStatus.SETTLED, "Market is not settled");
        
        Bet storage userBet = bets[_matchId][msg.sender];
        require(userBet.amount > 0, "You did not place a bet on this match");
        require(userBet.prediction == currentMarket.result, "Your prediction was not correct");

        uint256 winningPot;
        if (currentMarket.result == Prediction.HOME_TEAM) winningPot = currentMarket.potHome;
        else if (currentMarket.result == Prediction.AWAY_TEAM) winningPot = currentMarket.potAway;
        else winningPot = currentMarket.potDraw;

        require(winningPot > 0, "Winning pot is zero; no winnings to claim.");

        // Effect: Calculate payout before interaction.
        // The formula distributes the *entire* market pot (including losing bets)
        // among the winners, proportional to their stake in the winning pool.
        uint256 payout = (userBet.amount * currentMarket.totalPot) / winningPot;
        
        // Effect: Prevent re-claiming by zeroing out the bet amount.
        userBet.amount = 0;

        // Interaction: Transfer winnings to the user.
        bettingToken.transfer(msg.sender, payout);
        emit WinningsClaimed(_matchId, msg.sender, payout);
    }
}
